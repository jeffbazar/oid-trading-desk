#!/usr/bin/env python3
"""Import the published OID reference pages without correcting their financial data.

The default path only reads local files. --fetch retrieves an allowlisted bundle,
validates every response, archives it by content hash, then publishes one manifest
selecting that complete bundle. Original downloads and archived bundles stay intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

BASE_URL = "https://bold-tulip-nejq.here.now/"
SOURCE_FILES = (
    "index.html", "data-sources.html", "trader-intel.html", "catalysts.html",
    "soft-grader.html", "map.html", "chart.html", "peanut-news.json",
)
SOURCE_URLS = {name: BASE_URL + name for name in SOURCE_FILES}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}
SKIP_TEXT_TAGS = {"script", "style", "noscript"}
CLOCK_RE = re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\s+(?:PT|PDT|PST|ET|EDT|EST)", re.I)
ID_RE = re.compile(r"\b(?:OID|OT2|CB)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "section"


@dataclass
class Node:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list["Node | str"] = field(default_factory=list)
    parent: "Node | None" = field(default=None, repr=False)

    @property
    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


class DocumentParser(HTMLParser):
    """Small DOM builder with the implicit cell/row endings common in HTML tables."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"td", "th"} and self.stack[-1].tag in {"td", "th"}:
            self.stack.pop()
        if tag == "tr":
            for i in range(len(self.stack) - 1, 0, -1):
                if self.stack[i].tag == "tr":
                    self.stack = self.stack[:i]
                    break
        node = Node(tag, dict(attrs), parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag.lower():
                self.stack = self.stack[:i]
                return

    def handle_data(self, value):
        self.stack[-1].children.append(value)


def parse_document(value: str) -> Node:
    parser = DocumentParser()
    parser.feed(value)
    parser.close()
    return parser.root


def text_content(node: Node, preserve_lines=False) -> str:
    chunks = []
    for child in node.children:
        if isinstance(child, str):
            chunks.append(child)
        elif child.tag not in SKIP_TEXT_TAGS:
            if child.tag == "br":
                chunks.append("\n" if preserve_lines else " ")
            else:
                chunks.append(text_content(child, preserve_lines))
    if preserve_lines:
        return "".join(chunks).strip()
    return normalize_text(" ".join(chunks))


def first_class(node: Node, class_name: str) -> Node | None:
    return next((n for n in node.walk() if class_name in n.classes), None)


def class_text(node: Node, class_name: str) -> str | None:
    match = first_class(node, class_name)
    return text_content(match) if match else None


def extract_clock(value: str | None) -> str | None:
    match = CLOCK_RE.search(value or "")
    return match.group() if match else None


def extract_as_of(value: str | None) -> str | None:
    """Keep a published bare as-of date as a date, without inventing a clock."""
    clock = extract_clock(value)
    if clock:
        return clock
    match = re.search(r"\bas of\s+(\d{4}-\d{2}-\d{2})\b", value or "", re.I)
    return match.group(1) if match else None


def clock_iso(value: str | None) -> str | None:
    """Convert only complete published clocks; never invent a time for a bare date."""
    if not value:
        return None
    match = CLOCK_RE.fullmatch(value.strip())
    if not match:
        return None
    zone = "America/Los_Angeles" if re.search(r"\b(?:PT|PDT|PST)$", value, re.I) else "America/New_York"
    raw = re.sub(r"\s+(?:PT|PDT|PST|ET|EDT|EST)$", "", value.strip(), flags=re.I)
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M:%S %p", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw.upper(), fmt).replace(tzinfo=ZoneInfo(zone))
            return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    return None


def content_links(node: Node, source_url: str) -> list[dict]:
    return [{"label": text_content(n), "url": urljoin(source_url, n.attrs["href"]),
             "original_url": n.attrs["href"]}
            for n in node.walk() if n.tag == "a" and n.attrs.get("href")]


def extract_cell(node: Node, source_url: str) -> dict:
    result = {"text": text_content(node), "links": content_links(node, source_url),
              "attributes": dict(node.attrs)}
    titles = [{"tag": n.tag, "text": text_content(n), "title": n.attrs["title"]}
              for n in node.walk() if n.attrs.get("title")]
    if titles:
        result["title"] = titles[0]["title"]
        result["titles"] = titles
    details = [{"tag": n.tag, "text": text_content(n, preserve_lines=n.tag == "pre"),
                "attributes": dict(n.attrs), "title": n.attrs.get("title")}
               for n in node.walk() if n.tag in {"details", "summary", "pre"} or "rat-pop" in n.classes]
    if details:
        result["details"] = details
    return result


def extract_table(table: Node, source_url: str, section_id: str) -> tuple[list[str], list[dict]]:
    headers, rows = [], []
    duplicates = {}
    for tr in table.walk():
        if tr.tag != "tr" or any(a.tag == "table" and a is not table for a in tr.ancestors()):
            continue
        cells = [n for n in tr.children if isinstance(n, Node) and n.tag in {"th", "td"}]
        if not cells:
            continue
        if all(c.tag == "th" for c in cells):
            if not headers:
                headers = [text_content(c) for c in cells]
            continue
        values = [extract_cell(c, source_url) for c in cells]
        identity = digest(json.dumps(values, ensure_ascii=False, sort_keys=True))[:16]
        duplicates[identity] = duplicates.get(identity, 0) + 1
        suffix = "" if duplicates[identity] == 1 else f"-{duplicates[identity]}"
        row = {"id": f"{section_id}:row:{identity}{suffix}", "cells": values,
               "attributes": dict(tr.attrs)}
        if "group" in tr.classes:
            row["group_separator"] = True
        elif "drawer-row" in tr.classes:
            row["detail_row"] = True
            if rows and not any(rows[-1].get(flag) for flag in ("detail_row", "group_separator", "empty_state")):
                row["parent_row_id"] = rows[-1]["id"]
        elif len(cells) == 1 and (cells[0].attrs.get("colspan") or "empty" in cells[0].classes):
            row["empty_state"] = True
        row["published_ids"] = sorted(set(ID_RE.findall(" ".join(c["text"] + " " + c.get("title", "") for c in values))))
        rows.append(row)
    return headers, rows


def extract_header_rows(table: Node, source_url: str) -> list[dict]:
    """Retain header descriptions/links as well as the simple header-name list."""
    result = []
    for tr in table.walk():
        if tr.tag != "tr" or any(a.tag == "table" and a is not table for a in tr.ancestors()):
            continue
        cells = [n for n in tr.children if isinstance(n, Node) and n.tag in {"td", "th"}]
        if cells and all(c.tag == "th" for c in cells):
            result.append({"attributes": dict(tr.attrs), "cells": [extract_cell(c, source_url) for c in cells]})
    return result


def extract_card(node: Node, source_url: str, section_id: str) -> dict:
    card = extract_cell(node, source_url)
    card["id"] = f"{section_id}:card:{digest(json.dumps(card, sort_keys=True, ensure_ascii=False))[:16]}"
    label = (class_text(node, "k") or class_text(node, "f3-k") or class_text(node, "lid")
             or class_text(node, "mb-k") or class_text(node, "tl-sym") or class_text(node, "metric-k"))
    value = (class_text(node, "v") or class_text(node, "f3-v") or class_text(node, "mb-score")
             or class_text(node, "tl-px") or class_text(node, "metric-v"))
    if label:
        card["label"] = label
    if value:
        card["value"] = value
    return card


def parse_page(value: str, key: str, source: dict) -> tuple[dict, Node]:
    document = parse_document(value)
    if not any(n.tag == "html" for n in document.walk()) or not any(n.tag == "body" for n in document.walk()):
        raise ValueError(f"{key}.html must contain an HTML document with a body")
    body = next((n for n in document.walk() if n.tag == "body"), document)
    title_node = next((n for n in document.walk() if n.tag == "title"), None)
    h1 = next((n for n in body.walk() if n.tag == "h1"), None)
    title = text_content(title_node) if title_node else text_content(h1) if h1 else key
    sections, used = [], {}

    def new_section(title: str, attributes=None) -> dict:
        part = slug(title)
        used[part] = used.get(part, 0) + 1
        suffix = "" if used[part] == 1 else f"-{used[part]}"
        result = {"id": f"{key}:{part}{suffix}", "title": title, "headers": [],
                  "rows": [], "notes": [], "cards": [], "attributes": attributes or {}}
        sections.append(result)
        return result

    current = new_section(text_content(h1) if h1 else title)
    note_classes = {"note", "warn", "rules", "zero", "sub", "callout", "totals-bar",
                    "note-chip", "mb-sub", "f3-note", "quota-panel", "ds-summary", "footer"}
    card_classes = {"card", "f3-card", "lesson-card", "lesson", "qcard", "mb-pill", "mkt-idx", "metric-chip"}
    note_nodes = set()
    for node in body.walk():
        if any(a.tag in {"table", "script", "style", "nav"} or "tabs" in a.classes for a in node.ancestors()):
            continue
        if node.tag in {"h2", "h3", "h4", "h5", "h6"}:
            current = new_section(text_content(node), dict(node.attrs))
        elif node.tag == "div" and "f3-head" in node.classes:
            current = new_section(text_content(node), dict(node.attrs))
        elif "macro-banner" in node.classes:
            current = new_section(class_text(node, "mb-title") or "Macro checks", dict(node.attrs))
        elif node.tag == "details" and "mkt-detail" in node.classes:
            # This is a section container, not one rationale. Preserve its child
            # summary/cards/notes under their own headings instead of attributing
            # its entire macro text to the preceding closed-trade table.
            current = new_section(class_text(node, "mkt-title") or "Market detail", dict(node.attrs))
        elif node.tag == "table":
            headers, rows = extract_table(node, source["url"], current["id"])
            header_rows = extract_header_rows(node, source["url"])
            if current["headers"] and headers != current["headers"]:
                current = new_section(current["title"] + " · additional table")
                headers, rows = extract_table(node, source["url"], current["id"])
            current["headers"] = headers
            current["header_cells"] = header_rows[0]["cells"] if header_rows else []
            current["rows"].extend(rows)
            current.setdefault("tables", []).append({"attributes": dict(node.attrs), "headers": headers,
                                                     "header_rows": header_rows,
                                                     "row_ids": [r["id"] for r in rows]})
        elif node.classes & card_classes:
            # Parent cards already preserve their complete descendant text/links.
            if not any(a.classes & card_classes for a in node.ancestors()):
                current["cards"].append(extract_card(node, source["url"], current["id"]))
        elif (node.tag in {"p", "pre", "footer", "ul", "ol", "details", "summary"} or node.classes & note_classes):
            if not any(id(a) in note_nodes or a.classes & card_classes for a in node.ancestors()):
                text = text_content(node, preserve_lines=node.tag == "pre")
                if text:
                    current["notes"].append(text)
                    current.setdefault("note_details", []).append(extract_cell(node, source["url"]))
                    note_nodes.add(id(node))
    body_text = text_content(body)
    built = re.search(r"\bBuilt\s+(" + CLOCK_RE.pattern + r")", body_text, re.I)
    page = {"key": key, "title": title, "built_at": built.group(1) if built else None,
            "source": source, "sections": sections}
    page["published_clocks"] = list(dict.fromkeys(CLOCK_RE.findall(body_text)))
    page["navigation"] = [l for n in body.walk() if "tabs" in n.classes for l in content_links(n, source["url"])]
    return page, document


def enrich_row(row: dict, section: dict, page_key: str) -> dict:
    return {**row, "headers": section["headers"], "section_id": section["id"],
            "section_title": section["title"], "source_page": page_key}


def decimal_value(value: str) -> Decimal | None:
    value = value.replace("−", "-").replace(",", "").replace("$", "").strip()
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", value):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def row_field(row: dict, name: str) -> str:
    wanted = normalize_text(name).lower()
    for header, cell in zip(row.get("headers", []), row["cells"]):
        if normalize_text(header).lower() == wanted:
            return cell["text"]
    return ""


def validation_flags(snapshot: dict) -> list[dict]:
    flags = [{"code": "NAV_UNAVAILABLE", "severity": "info", "title": "Fund return unavailable",
              "message": "Published ticket/debit summaries do not establish cash, external flows, sleeve capital or reconciled NAV. No fund return is inferred."},
             {"code": "DISTINCT_SOURCE_CLOCKS", "severity": "info", "title": "Page rebuild is not quote freshness",
              "message": "Build, marks, macro judgment, feed success and collection clocks are separate. Retained weekend observations are not automatically outages.",
              "evidence": snapshot["observed"]}]
    for row in snapshot["closed_trades"]:
        contract = row_field(row, "Contract")
        if "credit" in contract.lower():
            flags.append({"code": "CREDIT_SPREAD_SIGN_REVIEW", "severity": "warning",
                          "title": "Verify credit-spread accounting", "row_id": row["id"],
                          "message": "Published credit-spread outcomes require signed-leg/cashflow verification. A shrinking closing debit may be a profit; original values remain unchanged.",
                          "evidence": {"contract": contract, "reported_pnl": row_field(row, "P&L $")}})
        entry, exit = row_field(row, "In"), row_field(row, "Out")
        for field_name, value in (("In", entry), ("Out", exit)):
            if value and not clock_iso(value):
                flags.append({"code": "IMPRECISE_TRADE_CLOCK", "severity": "warning",
                              "title": "Trade time is imprecise", "row_id": row["id"],
                              "message": f"The published {field_name} time is retained as written; no precise execution time is invented.", "evidence": value})
        cost = decimal_value(row_field(row, "Cost"))
        mark = decimal_value(row_field(row, "Exit/Mark"))
        qty = decimal_value(row_field(row, "Qty"))
        pnl = decimal_value(row_field(row, "P&L $"))
        if None not in (cost, mark, qty, pnl) and "credit" not in contract.lower():
            difference = (mark - cost) * qty * 100 - pnl
            # Published cent-rounded marks can differ by <=$0.50/standard contract.
            if abs(difference) > Decimal("0.51") * abs(qty):
                flags.append({"code": "PUBLISHED_PNL_RECONCILIATION", "severity": "warning",
                              "title": "Published P&L needs reconciliation", "row_id": row["id"],
                              "message": "Displayed cost/mark/quantity do not reconcile under an illustrative standard-100 long-premium comparison beyond cent-rounding tolerance. Costs, actual deliverables and unrounded values must be verified; no corrected return is asserted.",
                              "evidence": {"cost": str(cost), "mark": str(mark), "qty": str(qty), "reported_pnl": str(pnl)}})
        for cell in row["cells"]:
            for detail in cell.get("titles", []):
                title = detail["title"]
                if title.startswith(("MFE $", "MAE $")):
                    clock = extract_clock(title)
                    stamp, lo, hi = clock_iso(clock), clock_iso(entry), clock_iso(exit)
                    if stamp and lo and hi and not lo <= stamp <= hi:
                        flags.append({"code": "EXTREMA_OUTSIDE_RECORDED_INTERVAL", "severity": "warning",
                                      "title": "Excursion timestamp needs review", "row_id": row["id"],
                                      "message": "A published MFE/MAE timestamp is outside the recorded holding interval. Preserve it as a reported value rather than calibrated executable performance.",
                                      "evidence": {"entry": entry, "exit": exit, "extreme": title}})
    return flags


def build_snapshot(payloads: dict[str, bytes], provenance: dict[str, dict], imported_at=None) -> dict:
    missing = set(SOURCE_FILES) - payloads.keys()
    if missing:
        raise ValueError("Missing required source files: " + ", ".join(sorted(missing)))
    pages, documents = [], {}
    for name in SOURCE_FILES:
        if not name.endswith(".html"):
            continue
        page, document = parse_page(payloads[name].decode("utf-8-sig"), name.removesuffix(".html"), provenance[name])
        pages.append(page)
        documents[page["key"]] = document
    index = next(p for p in pages if p["key"] == "index")
    headings = [s["title"].lower() for s in index["sections"]]
    for required in ("open (rose)", "open (hal)", "recently closed"):
        if not any(h.startswith(required) for h in headings):
            raise ValueError("index.html is missing the published " + required + " section")
    document = documents["index"]
    body = next((n for n in document.walk() if n.tag == "body"), document)
    body_text = text_content(body)
    marks_match = re.search(r"Marks refresh:\s*(" + CLOCK_RE.pattern + r")", body_text, re.I)
    macro_banner = first_class(body, "macro-banner")
    macro_at = extract_clock(class_text(macro_banner, "mb-sub")) if macro_banner else None
    judgments, metrics = [], []
    if macro_banner:
        for node in macro_banner.walk():
            if "mb-pill" in node.classes:
                score = class_text(node, "mb-score")
                judgments.append({"name": class_text(node, "mb-k"), "score": int(score) if score and re.fullmatch(r"[+-]?\d+", score) else None,
                                  "label": class_text(node, "mb-label"), "as_of": macro_at,
                                  "tone": next((c.removeprefix("soft-") for c in sorted(node.classes) if c.startswith("soft-")), None),
                                  "title": node.attrs.get("title"), "details": text_content(node),
                                  "attributes": dict(node.attrs)})
            elif "mb-chip" in node.classes:
                metrics.append({"name": class_text(node, "mb-chip-k"), "value": class_text(node, "mb-chip-v"),
                                "change": class_text(node, "daychip"), "title": node.attrs.get("title"),
                                "source": node.attrs.get("title"), "source_page": "index",
                                "as_of": extract_as_of(node.attrs.get("title")), "attributes": dict(node.attrs)})
    input_scores = [{"name": class_text(n, "metric-k"), "score": class_text(n, "metric-v"),
                     "title": n.attrs.get("title"), "attributes": dict(n.attrs)}
                    for n in body.walk() if "metric-chip" in n.classes]
    positions = {"rose": [], "hal": []}
    closed, watches = [], []
    for section in index["sections"]:
        rows = [enrich_row(r, section, "index") for r in section["rows"]
                if not r.get("empty_state") and not r.get("group_separator") and not r.get("detail_row")]
        lower = section["title"].lower()
        if lower.startswith("open (rose)"):
            positions["rose"].extend(rows)
        elif lower.startswith("open (hal)"):
            positions["hal"].extend(rows)
        elif lower.startswith("recently closed"):
            closed.extend(rows)
        elif "watch" in lower or "key levels" in lower:
            watches.extend(rows)
    news_document = json.loads(payloads["peanut-news.json"])
    if not isinstance(news_document, dict) or not isinstance(news_document.get("items"), list):
        raise ValueError("peanut-news.json must contain an object with an items array")
    if any(not isinstance(item, dict) for item in news_document["items"]):
        raise ValueError("Every peanut-news.json item must be an object")
    news = [{**item, "source_provenance": provenance["peanut-news.json"]} for item in news_document["items"]]
    bundle = digest("\n".join(name + ":" + digest(payloads[name]) for name in SOURCE_FILES))
    snapshot = {"schema_version": "oid-published-snapshot-v1", "snapshot_id": bundle,
                "imported_at": imported_at or utc_now(), "mode": "OBSERVED_PUBLISHED_RESEARCH_PAPER_SNAPSHOT",
                "provenance": [provenance[n] for n in SOURCE_FILES], "pages": pages,
                "sections": index["sections"], "positions": positions, "closed_trades": closed,
                "watches": watches, "news": news,
                "news_metadata": {k: v for k, v in news_document.items() if k != "items"},
                "observed": {"built_at": index["built_at"], "marks_at": marks_match.group(1) if marks_match else None,
                             "macro_at": macro_at},
                "macro": {"judgments": judgments, "metrics": metrics, "input_scores": input_scores,
                          "context": [{"id": s["id"], "title": s["title"], "notes": s["notes"], "cards": s["cards"]}
                                      for s in index["sections"] if "macro" in s["title"].lower()]}}
    snapshot["observed_iso"] = {k: clock_iso(v) for k, v in snapshot["observed"].items()}
    snapshot["data_validation"] = validation_flags(snapshot)
    return snapshot


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def load_local(raw_dir: Path, collected_at: str | None = None) -> tuple[dict, dict]:
    pointer = raw_dir / "current.json"
    manifest = json.loads(pointer.read_text()) if pointer.exists() else None
    payloads, sources = {}, {}
    for name in SOURCE_FILES:
        path = raw_dir / name
        if manifest:
            path = (raw_dir / manifest["files"][name]).resolve()
            if not path.is_relative_to(raw_dir.parent.resolve()):
                raise ValueError("Current bundle pointer must remain inside the data directory")
        payloads[name] = path.read_bytes()
        if manifest and name in manifest.get("sources", {}):
            source = dict(manifest["sources"][name])
            if source["sha256"] != digest(payloads[name]):
                raise ValueError("Archived source hash mismatch: " + name)
            sources[name] = source
        else:
            sources[name] = {"url": SOURCE_URLS[name], "file": str(path.resolve()),
                             "sha256": digest(payloads[name]),
                             "collected_at": collected_at or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                             "collected_at_basis": "provided_download_time" if collected_at else "local_file_mtime_not_independent_network_receipt"}
    return payloads, sources


class AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, new_url):
        if new_url.split("/", 3)[:3] != BASE_URL.split("/", 3)[:3]:
            raise ValueError("Source redirect left the allowlisted host")
        return super().redirect_request(request, fp, code, msg, headers, new_url)


def fetch_sources(opener=None) -> tuple[dict, dict]:
    opener = opener or urllib.request.build_opener(AllowlistedRedirectHandler()).open
    payloads, sources = {}, {}
    for name in SOURCE_FILES:
        request = urllib.request.Request(SOURCE_URLS[name], headers={"User-Agent": "OID-reference-importer/1.0"})
        with opener(request, timeout=30) as response:
            payload = response.read(5 * 1024 * 1024 + 1)
            if len(payload) > 5 * 1024 * 1024:
                raise ValueError("Source response too large: " + name)
            if response.geturl().split("/", 3)[:3] != SOURCE_URLS[name].split("/", 3)[:3]:
                raise ValueError("Source redirect left the allowlisted host: " + name)
            payloads[name] = payload
            sources[name] = {"url": SOURCE_URLS[name], "file": name, "sha256": digest(payload),
                             "collected_at": utc_now(), "collected_at_basis": "network_response_received"}
    # Complete parsing before the caller is permitted to publish any source files.
    build_snapshot(payloads, sources)
    return payloads, sources


def archive_bundle(data_dir: Path, payloads: dict, sources: dict) -> tuple[Path, dict]:
    bundle_id = digest("\n".join(name + ":" + digest(payloads[name]) for name in SOURCE_FILES))
    destination = data_dir / "reference-snapshots" / bundle_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = Path(tempfile.mkdtemp(prefix=".bundle-", dir=destination.parent))
        try:
            for name, value in payloads.items():
                (temporary / name).write_bytes(value)
            atomic_json(temporary / "manifest.json", {"bundle_id": bundle_id, "sources": sources})
            try:
                os.rename(temporary, destination)
            except FileExistsError:
                pass
        finally:
            if temporary.exists():
                for child in temporary.iterdir():
                    child.unlink()
                temporary.rmdir()
    for name in SOURCE_FILES:
        if digest((destination / name).read_bytes()) != digest(payloads[name]):
            raise ValueError("Immutable archive differs from its content hash: " + name)
    published_sources = {name: {**sources[name], "file": str((destination / name).resolve())} for name in SOURCE_FILES}
    return destination, published_sources


def run_import(raw_dir: Path, output: Path, *, fetch=False, collected_at=None, opener=None) -> dict:
    if fetch:
        payloads, sources = fetch_sources(opener)
    else:
        payloads, sources = load_local(raw_dir, collected_at)
    # Validate first: failures must not replace a previous valid snapshot.
    build_snapshot(payloads, sources)
    archive, sources = archive_bundle(raw_dir.parent, payloads, sources)
    snapshot = build_snapshot(payloads, sources)
    atomic_json(output, snapshot)
    if fetch:
        atomic_json(raw_dir / "current.json", {"bundle_id": snapshot["snapshot_id"],
                    "files": {n: os.path.relpath(archive / n, raw_dir) for n in SOURCE_FILES},
                    "sources": sources})
    return snapshot


def main(argv=None):
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=root / "data" / "raw")
    parser.add_argument("--output", type=Path, default=root / "data" / "snapshot.json")
    parser.add_argument("--fetch", action="store_true", help="Fetch the complete allowlisted bundle before publishing it")
    parser.add_argument("--collected-at", help="Known RFC3339 receipt time for the existing local downloads")
    args = parser.parse_args(argv)
    if args.collected_at:
        receipt = datetime.fromisoformat(args.collected_at.replace("Z", "+00:00"))
        if receipt.tzinfo is None:
            parser.error("--collected-at must include a timezone offset or Z")
    snapshot = run_import(args.raw_dir, args.output, fetch=args.fetch, collected_at=args.collected_at)
    print(json.dumps({"snapshot_id": snapshot["snapshot_id"], "pages": len(snapshot["pages"]),
                      "open_rose": len(snapshot["positions"]["rose"]), "open_hal": len(snapshot["positions"]["hal"]),
                      "closed_rows": len(snapshot["closed_trades"]), "watches": len(snapshot["watches"]),
                      "news": len(snapshot["news"]), "validation_flags": len(snapshot["data_validation"]),
                      "output": str(args.output.resolve())}, indent=2))


if __name__ == "__main__":
    main()
