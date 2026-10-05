"""Importer checks focused on source preservation and safe snapshot publication."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import import_snapshot as importer


def html(body, title="OID fixture"):
    return f"<!doctype html><html><head><title>{title}</title></head><body>{body}</body></html>".encode()


def table(headers, cells, attributes=""):
    return ("<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in headers)
            + "</tr></thead><tbody><tr " + attributes + ">"
            + "".join(f"<td>{c}</td>" for c in cells) + "</tr></tbody></table>")


def fixture_payloads():
    result = {name: html("<h1>" + name + "</h1><p>Published source.</p>")
              for name in importer.SOURCE_FILES if name.endswith(".html")}
    result["index.html"] = html("""
      <h1>OID Live Book</h1><p>Built 2026-10-04 5:26 PM PT</p>
      <p>Marks refresh: 2026-10-02 1:02 PM PT</p>
      <div class="macro-banner"><span class="mb-title">Macro checks</span>
        <div class="mb-sub">Judgment 2026-10-02 5:54 AM PT</div>
        <div class="mb-pill" title="Broad judgment"><b class="mb-k">Daily Macro</b>
          <b class="mb-score">+1</b><b class="mb-label">warm</b></div>
        <div class="mb-pill" title="Duration judgment"><b class="mb-k">Macro Tech</b>
          <b class="mb-score">+2</b><b class="mb-label">warm</b></div>
        <div class="mb-chip" title="Treasury source 2026-10-02 5:54 AM PT">
          <b class="mb-chip-k">10Y</b><b class="mb-chip-v">4.96%</b><b class="daychip">−6bp</b></div>
      </div>
      <div class="metric-chip"><b class="metric-k">Rates</b><b class="metric-v">+2</b></div>
      <div class="metric-chip"><b class="metric-k">Oil</b><b class="metric-v">+1</b></div>
      <h2>Open (Rose) · live marks vs cost basis</h2>
      <table><tr><th>Agent</th><th>Contract</th></tr>
        <tr><td colspan="2" class="empty">No open tickets.</td></tr></table>
      <h2>Open (Hal) · live marks vs cost basis</h2>
      <table><tr><th>Agent</th><th>Contract</th></tr>
        <tr id="published-hal"><td>Hal</td><td>NVDA Jan 15 2027 150 call</td></tr></table>
      <h2>Soft watches · research / color only</h2>
      <table><tr><th>Sym</th><th>Notes</th></tr>
        <tr data-kind="research"><td>NVDA</td><td>Supplier watch — unconfirmed</td></tr></table>
      <h2>Recently closed / invalidated</h2>
    """ + table(
        ["Agent", "Symbol", "Contract", "Why", "In", "Out", "Cost", "Qty", "Exit/Mark", "P&amp;L $", "MFE · time"],
        ["Rose", "NVDA", "NVDA Oct 16 2026 150 call", "Thesis invalidation",
         "2026-10-01 9:40 AM PT", "2026-10-02 10:00 AM PT", "2.00", "1", "2.25", "+25.00",
         '<span title="MFE $40.00 · 2026-10-01 11:00 AM PT">+20%</span>'],
        'id="trade-one" data-trade-id="OID-20261001-R-01"'))
    result["chart.html"] = html("""
      <h1>Chart Bot daily read</h1><p>RS is daily close relative return, not a forecast.</p>
      <table><tr><th>Symbol</th><th>SMA200</th></tr>
        <tr class="group"><td colspan="2">UNAVAILABLE · 1</td></tr>
        <tr data-history="insufficient"><td>SPCX</td><td>—</td></tr></table>
    """)
    result["soft-grader.html"] = html("""
      <h1>Soft Grader</h1><h2>Snapshot fields</h2>
      <h3>Compact numeric state</h3><ul><li>symbol</li><li>age_s</li></ul>
      <h3>Hard gates that always win</h3>
      <ul><li>freshness (RH live ≤120s)</li><li>Soft C never alone</li></ul>
      <h2>Details</h2><details><summary>Authority</summary><p>zero execution</p></details>
    """)
    result["peanut-news.json"] = json.dumps({
        "updated_at": "2026-10-04T23:26:00Z", "mode": "reported judgment",
        "items": [{"id": "story-1", "headline": "AI supplier — source claim", "score": 7,
                   "probability": None, "published_at": "2026-10-02T13:30:00Z", "symbols": ["NVDA"],
                   "custom_nested_field": {"source_status": "unconfirmed"}}],
    }, ensure_ascii=False).encode()
    return result


def provenance(payloads):
    return {name: {"url": importer.SOURCE_URLS[name], "file": name,
                   "sha256": importer.digest(value), "collected_at": "2026-10-05T00:30:00Z",
                   "collected_at_basis": "fixture_receipt"} for name, value in payloads.items()}


def fixture_snapshot(payloads=None):
    values = payloads or fixture_payloads()
    return importer.build_snapshot(values, provenance(values), imported_at="2026-10-05T00:31:00Z")


class FakeResponse:
    def __init__(self, url, payload):
        self.url, self.payload = url, payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.url

    def read(self, size):
        return self.payload[:size]


def fake_opener(payloads, *, fail_on=None, redirect=None):
    def open_response(request, timeout):
        name = request.full_url.rsplit("/", 1)[-1]
        if name == fail_on:
            raise OSError("Fixture download interrupted")
        return FakeResponse(redirect or request.full_url, payloads[name])
    return open_response


class SourcePreservationTests(unittest.TestCase):
    def test_full_cell_details_titles_attributes_and_links_are_retained(self):
        source = {"url": importer.BASE_URL + "index.html"}
        page, _ = importer.parse_page(html("""
          <h1>Book</h1><h2>Closed</h2><table id="closed"><tr><th>Why</th></tr>
          <tr id="row" data-agent="Rose"><td title="Original rationale">
            <a href="trader-intel.html#claim">R&amp;D evidence</a>
            <details><summary>More</summary><pre>Line 1\nLine 2 — preserved</pre></details>
            <span title="MFE $40 · 2026-10-01 11:00 AM PT">20%</span> OID-20261001-R-01
          </td></tr></table>
        """).decode(), "index", source)
        row = page["sections"][1]["rows"][0]
        cell = row["cells"][0]
        self.assertEqual(row["attributes"]["data-agent"], "Rose")
        self.assertEqual(row["published_ids"], ["OID-20261001-R-01"])
        self.assertEqual(cell["title"], "Original rationale")
        self.assertEqual(len(cell["titles"]), 2)
        self.assertEqual(cell["links"][0]["label"], "R&D evidence")
        self.assertEqual(cell["links"][0]["url"], importer.BASE_URL + "trader-intel.html#claim")
        self.assertEqual(next(d["text"] for d in cell["details"] if d["tag"] == "pre"), "Line 1\nLine 2 — preserved")

    def test_implicit_row_and_cell_endings_keep_all_table_values(self):
        page, _ = importer.parse_page(html("<h1>Book</h1><table><tr><th>A<th>B<tr><td>1<td>2<tr><td>3<td>4</table>").decode(), "index", {"url": importer.BASE_URL})
        section = page["sections"][0]
        self.assertEqual(section["headers"], ["A", "B"])
        self.assertEqual([[c["text"] for c in r["cells"]] for r in section["rows"]], [["1", "2"], ["3", "4"]])

    def test_header_titles_links_and_attributes_are_retained(self):
        page, _ = importer.parse_page(html('''<h1>Book</h1><table><tr data-header="primary">
          <th title="Reported return, not fund NAV" class="num"><a href="data-sources.html">P&amp;L %</a></th>
          </tr><tr><td>+10.0%</td></tr></table>''').decode(), "index", {"url": importer.BASE_URL})
        section = page["sections"][0]
        self.assertEqual(section["headers"], ["P&L %"])
        self.assertEqual(section["header_cells"][0]["title"], "Reported return, not fund NAV")
        self.assertEqual(section["header_cells"][0]["links"][0]["url"], importer.BASE_URL + "data-sources.html")
        self.assertEqual(section["tables"][0]["header_rows"][0]["attributes"]["data-header"], "primary")

    def test_empty_open_state_is_preserved_but_is_not_a_position(self):
        snapshot = fixture_snapshot()
        self.assertEqual(snapshot["positions"]["rose"], [])
        self.assertEqual(len(snapshot["positions"]["hal"]), 1)
        section = next(s for s in snapshot["sections"] if s["title"].startswith("Open (Rose)"))
        self.assertTrue(section["rows"][0]["empty_state"])
        self.assertEqual(section["rows"][0]["cells"][0]["text"], "No open tickets.")

    def test_chart_group_rows_are_distinct_from_empty_or_missing_data(self):
        snapshot = fixture_snapshot()
        chart = next(p for p in snapshot["pages"] if p["key"] == "chart")
        rows = chart["sections"][0]["rows"]
        self.assertTrue(rows[0]["group_separator"])
        self.assertNotIn("empty_state", rows[0])
        self.assertEqual(rows[1]["cells"][1]["text"], "—")
        self.assertNotIn("empty_state", rows[1])

    def test_lists_and_standalone_details_preserve_gates(self):
        snapshot = fixture_snapshot()
        grader = next(p for p in snapshot["pages"] if p["key"] == "soft-grader")
        fields = next(s for s in grader["sections"] if s["title"] == "Compact numeric state")
        gates = next(s for s in grader["sections"] if s["title"] == "Hard gates that always win")
        details = next(s for s in grader["sections"] if s["title"] == "Details")
        self.assertIn("age_s", " ".join(fields["notes"]))
        self.assertIn("RH live ≤120s", " ".join(gates["notes"]))
        self.assertIn("zero execution", " ".join(details["notes"]))

    def test_judgments_are_preserved_without_summing_the_inputs(self):
        snapshot = fixture_snapshot()
        self.assertEqual([j["score"] for j in snapshot["macro"]["judgments"]], [1, 2])
        self.assertEqual([j["label"] for j in snapshot["macro"]["judgments"]], ["warm", "warm"])
        self.assertEqual([i["score"] for i in snapshot["macro"]["input_scores"]], ["+2", "+1"])
        self.assertEqual(snapshot["macro"]["metrics"][0]["value"], "4.96%")
        self.assertEqual(snapshot["macro"]["metrics"][0]["change"], "−6bp")
        self.assertIn("Treasury source", snapshot["macro"]["metrics"][0]["source"])

    def test_build_marks_macro_and_receipt_clocks_remain_distinct(self):
        snapshot = fixture_snapshot()
        self.assertEqual(snapshot["observed"]["built_at"], "2026-10-04 5:26 PM PT")
        self.assertEqual(snapshot["observed_iso"]["marks_at"], "2026-10-02T20:02:00Z")
        self.assertEqual(snapshot["observed_iso"]["macro_at"], "2026-10-02T12:54:00Z")
        self.assertNotEqual(snapshot["provenance"][0]["collected_at"], snapshot["observed_iso"]["marks_at"])
        self.assertIsNone(importer.clock_iso("2026-10-02"))
        self.assertIsNone(importer.clock_iso("2026-10-02 after close"))

    def test_news_custom_fields_and_nulls_are_unchanged(self):
        payloads = fixture_payloads()
        snapshot = fixture_snapshot(payloads)
        original = json.loads(payloads["peanut-news.json"])["items"][0]
        restored = {k: v for k, v in snapshot["news"][0].items() if k != "source_provenance"}
        self.assertEqual(restored, original)
        self.assertEqual(snapshot["news_metadata"]["mode"], "reported judgment")

    def test_row_ids_are_deterministic_and_duplicate_rows_are_unique(self):
        payloads = fixture_payloads()
        payloads["data-sources.html"] = html("<h1>Sources</h1><table><tr><th>Source</th></tr><tr><td>SEC</td></tr><tr><td>SEC</td></tr></table>")
        first = fixture_snapshot(payloads)
        second = fixture_snapshot(payloads)
        page = next(p for p in first["pages"] if p["key"] == "data-sources")
        rows = page["sections"][0]["rows"]
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertNotEqual(rows[0]["id"], rows[1]["id"])
        self.assertTrue(rows[1]["id"].endswith("-2"))

    def test_different_table_headers_create_addressable_sections(self):
        value = html("<h1>Book</h1><h2>Mixed</h2>" + table(["A"], ["1"]) + table(["B", "C"], ["2", "3"]))
        page, _ = importer.parse_page(value.decode(), "index", {"url": importer.BASE_URL})
        self.assertEqual([s["headers"] for s in page["sections"] if s["rows"]], [["A"], ["B", "C"]])
        self.assertEqual(len({s["id"] for s in page["sections"]}), len(page["sections"]))
        self.assertTrue(all(row["id"].startswith(s["id"] + ":row:") for s in page["sections"] for row in s["rows"]))

    def test_open_position_details_are_linked_not_treated_as_empty(self):
        values = fixture_payloads()
        index = values["index.html"].decode().replace(
            '<tr id="published-hal"><td>Hal</td><td>NVDA Jan 15 2027 150 call</td></tr>',
            '<tr id="published-hal" class="main-row"><td>Hal</td><td>NVDA Jan 15 2027 150 call</td></tr>'
            '<tr class="drawer-row" hidden><td colspan="2"><details><summary>Greeks</summary>delta 0.65</details></td></tr>')
        values["index.html"] = index.encode()
        snapshot = fixture_snapshot(values)
        self.assertEqual(len(snapshot["positions"]["hal"]), 1)
        section = next(s for s in snapshot["sections"] if s["title"].startswith("Open (Hal)"))
        drawer = section["rows"][1]
        self.assertTrue(drawer["detail_row"])
        self.assertNotIn("empty_state", drawer)
        self.assertEqual(drawer["parent_row_id"], snapshot["positions"]["hal"][0]["id"])
        self.assertIn("delta 0.65", drawer["cells"][0]["text"])

    def test_source_as_of_date_remains_date_precision(self):
        self.assertEqual(importer.extract_as_of("10Y Treasury · as of 2026-09-22"), "2026-09-22")
        self.assertIsNone(importer.clock_iso(importer.extract_as_of("10Y Treasury · as of 2026-09-22")))

    def test_market_detail_notes_are_not_assigned_to_closed_trades(self):
        values = fixture_payloads()
        values["index.html"] = values["index.html"].replace(b"</body>", b'''<details class="mkt-detail">
          <summary class="mkt-detail-sum"><span class="mkt-title">Market detail</span>Session clock</summary>
          <div class="f3-head">Macro rates</div><div class="f3-note">Treasury as of Sep22</div>
          </details></body>''')
        snapshot = fixture_snapshot(values)
        closed = next(s for s in snapshot["sections"] if s["title"].startswith("Recently closed"))
        macro = next(s for s in snapshot["sections"] if s["title"] == "Macro rates")
        self.assertNotIn("Treasury as of Sep22", " ".join(closed["notes"]))
        self.assertIn("Treasury as of Sep22", " ".join(macro["notes"]))


class FinancialValidationTests(unittest.TestCase):
    def row(self, **values):
        headers = ["Contract", "In", "Out", "Cost", "Qty", "Exit/Mark", "P&L $", "MFE · time"]
        defaults = {"Contract": "NVDA Oct 16 150 call", "In": "2026-10-01 9:40 AM PT", "Out": "2026-10-02 10:00 AM PT",
                    "Cost": "2.00", "Qty": "1", "Exit/Mark": "2.25", "P&L $": "+25.00", "MFE · time": "+20%"}
        defaults.update(values)
        return {"id": "fixture-row", "headers": headers, "cells": [{"text": defaults[h]} for h in headers]}

    def flags(self, row):
        return importer.validation_flags({"closed_trades": [row], "observed": {"built_at": "retained"}})

    def test_credit_warning_retains_reported_sign_and_values(self):
        row = self.row(Contract="NVDA Oct 16 put credit spread", Cost="0.90", **{"Exit/Mark": "0.20", "P&L $": "−70.00"})
        original = copy.deepcopy(row)
        flags = self.flags(row)
        self.assertTrue(any(f["code"] == "CREDIT_SPREAD_SIGN_REVIEW" for f in flags))
        self.assertFalse(any(f["code"] == "PUBLISHED_PNL_RECONCILIATION" for f in flags))
        self.assertEqual(row, original)

    def test_long_premium_mismatch_flag_is_conditional_not_a_correction(self):
        row = self.row(Cost="8.65", **{"Exit/Mark": "3.80", "P&L $": "−467.50"})
        flags = self.flags(row)
        warning = next(f for f in flags if f["code"] == "PUBLISHED_PNL_RECONCILIATION")
        self.assertEqual(warning["evidence"]["reported_pnl"], "-467.50")
        self.assertIn("illustrative standard-100", warning["message"])
        self.assertEqual(importer.row_field(row, "P&L $"), "−467.50")

    def test_cent_rounded_prices_are_not_overflagged(self):
        row = self.row(**{"P&L $": "+25.49"})
        self.assertFalse(any(f["code"] == "PUBLISHED_PNL_RECONCILIATION" for f in self.flags(row)))

    def test_extrema_outside_holding_interval_are_flagged(self):
        row = self.row()
        row["cells"][-1]["titles"] = [{"title": "MFE $500 · 2026-10-03 11:00 AM PT"}]
        flags = self.flags(row)
        self.assertTrue(any(f["code"] == "EXTREMA_OUTSIDE_RECORDED_INTERVAL" for f in flags))

    def test_imprecise_exit_time_is_retained_without_inventing_timestamp(self):
        row = self.row(Out="2026-10-02 EOD")
        flags = self.flags(row)
        self.assertTrue(any(f["code"] == "IMPRECISE_TRADE_CLOCK" for f in flags))
        self.assertEqual(importer.row_field(row, "Out"), "2026-10-02 EOD")

    def test_no_nav_is_inferred_from_ticket_returns(self):
        snapshot = fixture_snapshot()
        self.assertTrue(any(f["code"] == "NAV_UNAVAILABLE" for f in snapshot["data_validation"]))
        self.assertNotIn("nav", snapshot)
        self.assertNotIn("fund_return", snapshot)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data = Path(self.temporary.name) / "data"
        self.raw = self.data / "raw"
        self.raw.mkdir(parents=True)
        self.payloads = fixture_payloads()
        for name, value in self.payloads.items():
            (self.raw / name).write_bytes(value)
        self.output = self.data / "snapshot.json"

    def test_local_import_preserves_originals_and_publishes_archival_provenance(self):
        before = {n: importer.digest((self.raw / n).read_bytes()) for n in importer.SOURCE_FILES}
        snapshot = importer.run_import(self.raw, self.output, collected_at="2026-10-05T00:30:00Z")
        self.assertEqual(before, {n: importer.digest((self.raw / n).read_bytes()) for n in importer.SOURCE_FILES})
        self.assertFalse((self.raw / "current.json").exists())
        for source in snapshot["provenance"]:
            self.assertIn("reference-snapshots", source["file"])
            self.assertEqual(importer.digest(Path(source["file"]).read_bytes()), source["sha256"])
            self.assertEqual(source["collected_at_basis"], "provided_download_time")

    def test_partial_fetch_does_not_replace_snapshot_or_select_bundle(self):
        importer.run_import(self.raw, self.output)
        before = self.output.read_bytes()
        with self.assertRaises(OSError):
            importer.run_import(self.raw, self.output, fetch=True, opener=fake_opener(self.payloads, fail_on="catalysts.html"))
        self.assertEqual(self.output.read_bytes(), before)
        self.assertFalse((self.raw / "current.json").exists())

    def test_invalid_json_or_html_cannot_publish_a_new_snapshot(self):
        importer.run_import(self.raw, self.output)
        before = self.output.read_bytes()
        for name, invalid in (("peanut-news.json", b'{"items": "broken"}'), ("chart.html", b"temporarily unavailable")):
            payloads = {**self.payloads, name: invalid}
            with self.subTest(source=name), self.assertRaises(ValueError):
                importer.run_import(self.raw, self.output, fetch=True, opener=fake_opener(payloads))
            self.assertEqual(self.output.read_bytes(), before)
            self.assertFalse((self.raw / "current.json").exists())

    def test_error_document_cannot_silently_replace_published_book(self):
        importer.run_import(self.raw, self.output)
        before = self.output.read_bytes()
        values = {**self.payloads, "index.html": html("<h1>Service unavailable</h1><p>Retry later</p>")}
        with self.assertRaisesRegex(ValueError, "missing the published"):
            importer.run_import(self.raw, self.output, fetch=True, opener=fake_opener(values))
        self.assertEqual(self.output.read_bytes(), before)
        self.assertFalse((self.raw / "current.json").exists())

    def test_missing_source_does_not_replace_previous_snapshot(self):
        importer.run_import(self.raw, self.output)
        before = self.output.read_bytes()
        (self.raw / "map.html").unlink()
        with self.assertRaises(FileNotFoundError):
            importer.run_import(self.raw, self.output)
        self.assertEqual(self.output.read_bytes(), before)

    def test_complete_fetch_selects_bundle_without_overwriting_original_downloads(self):
        updated = {**self.payloads, "chart.html": html("<h1>New chart publication</h1><p>New observation.</p>")}
        snapshot = importer.run_import(self.raw, self.output, fetch=True, opener=fake_opener(updated))
        pointer = json.loads((self.raw / "current.json").read_text())
        self.assertEqual(set(pointer["files"]), set(importer.SOURCE_FILES))
        self.assertEqual((self.raw / "chart.html").read_bytes(), self.payloads["chart.html"])
        local = importer.run_import(self.raw, self.output)
        self.assertEqual(local["snapshot_id"], snapshot["snapshot_id"])
        self.assertTrue(any(p["title"] == "OID fixture" and p["sections"][0]["title"] == "New chart publication" for p in local["pages"]))

    def test_existing_archive_is_verified_and_never_repaired_in_place(self):
        snapshot = importer.run_import(self.raw, self.output)
        source = next(s for s in snapshot["provenance"] if s["url"].endswith("chart.html"))
        archive = Path(source["file"])
        archive.write_bytes(b"tampered reference")
        before = self.output.read_bytes()
        with self.assertRaisesRegex(ValueError, "Immutable archive differs"):
            importer.run_import(self.raw, self.output)
        self.assertEqual(archive.read_bytes(), b"tampered reference")
        self.assertEqual(self.output.read_bytes(), before)

    def test_pointer_cannot_escape_data_directory(self):
        atomic_pointer = {"files": {n: "../../outside/" + n for n in importer.SOURCE_FILES}}
        importer.atomic_json(self.raw / "current.json", atomic_pointer)
        with self.assertRaisesRegex(ValueError, "inside the data directory"):
            importer.load_local(self.raw)

    def test_redirect_cannot_leave_allowlisted_host(self):
        with self.assertRaisesRegex(ValueError, "allowlisted host"):
            importer.fetch_sources(fake_opener(self.payloads, redirect="https://other.example/index.html"))

    def test_default_redirect_handler_blocks_other_hosts_before_following(self):
        request = importer.urllib.request.Request(importer.SOURCE_URLS["index.html"])
        handler = importer.AllowlistedRedirectHandler()
        with self.assertRaisesRegex(ValueError, "allowlisted host"):
            handler.redirect_request(request, None, 302, "Found", {}, "https://other.example/index.html")

    def test_oversized_source_is_rejected_before_publication(self):
        values = {**self.payloads, "index.html": b"x" * (5 * 1024 * 1024 + 1)}
        with self.assertRaisesRegex(ValueError, "too large"):
            importer.fetch_sources(fake_opener(values))


class DownloadedProductionRegressionTests(unittest.TestCase):
    """The downloaded reference remains the evidence; this is not a live request."""
    @unittest.skipUnless((ROOT / "data" / "raw" / "index.html").exists(), "Reference downloads absent")
    def test_downloaded_sources_preserve_all_published_rows_and_exact_clocks(self):
        # Assert the original reference download even when --fetch selects a newer bundle.
        payloads = {name: (ROOT / "data" / "raw" / name).read_bytes() for name in importer.SOURCE_FILES}
        sources = provenance(payloads)
        snapshot = importer.build_snapshot(payloads, sources)
        self.assertEqual(len(snapshot["pages"]), 7)
        self.assertEqual(snapshot["observed"]["built_at"], "2026-10-04 5:26 PM PT")
        self.assertEqual(snapshot["observed"]["marks_at"], "2026-10-02 1:02 PM PT")
        self.assertEqual(len(snapshot["closed_trades"]), 57)
        self.assertEqual(len(snapshot["watches"]), 88)
        self.assertEqual(snapshot["positions"], {"rose": [], "hal": []})
        self.assertEqual(len(snapshot["news"]), 10)
        chart = next(p for p in snapshot["pages"] if p["key"] == "chart")
        chart_rows = [r for s in chart["sections"] for r in s["rows"]]
        self.assertEqual(sum(not r.get("group_separator") and not r.get("empty_state") for r in chart_rows), 37)
        self.assertEqual(sum(bool(r.get("group_separator")) for r in chart_rows), 4)
        self.assertEqual([j["score"] for j in snapshot["macro"]["judgments"]], [1, 2])


if __name__ == "__main__":
    unittest.main()
