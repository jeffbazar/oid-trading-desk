#!/usr/bin/env python3
"""Peanut (News Alerts) bottom marquee for OID Live Book.

Store: paper-trades/peanut-news.json
Append alerts from Peanut routines; rebuild.py embeds a fixed bottom scroller.
Banner shows only alerts newer than the prior completed RTH close; full history
lives on news-archive.html. Research / paper only — zero RH orders.
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
root = Path(__file__).resolve().parent
STORE = root.parent / "paper-trades" / "peanut-news.json"
DASHBOARD_COPY = root / "peanut-news.json"

# paper-trades/market_session.py (prior RTH close + holidays)
_pt_dir = root.parent / "paper-trades"
if str(_pt_dir) not in sys.path:
    sys.path.insert(0, str(_pt_dir))
from market_session import prior_rth_close  # noqa: E402

MAX_ITEMS = 24
# Marquee: was 55s; ~55% slower (~1.55× duration) for readability
MARQUEE_DURATION_S = 85

BANNER_JS = r"""
(function () {
  "use strict";
  var banner = document.querySelector(".peanut-banner");
  if (!banner) return;

  var SEEN_KEY = "peanutNewsSeenIds";
  var SEEDED_KEY = "peanutNewsSeenSeeded";
  var SOUND_KEY = "peanutNewsSound";
  var POLL_MS = 15000;
  var BANNER_CUTOFF_ISO = "__BANNER_CUTOFF_ISO__";
  var seen = new Set();
  var soundOn = false;
  var audioContext = null;
  var pollBusy = false;

  function readSeen() {
    try {
      var raw = JSON.parse(localStorage.getItem(SEEN_KEY) || "[]");
      if (Array.isArray(raw)) raw.forEach(function (id) { if (id) seen.add(String(id)); });
    } catch (_) {}
  }

  function saveSeen() {
    try {
      var ids = Array.from(seen);
      localStorage.setItem(SEEN_KEY, JSON.stringify(ids));
    } catch (_) {}
  }

  function seedFromBanner() {
    var ids = banner.querySelectorAll("[data-peanut-id]");
    ids.forEach(function (node) {
      var id = node.getAttribute("data-peanut-id");
      if (id) seen.add(id);
    });
    saveSeen();
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>\"]/g, function (ch) {
      return {"&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;"}[ch];
    });
  }

  function fmtScore(score) {
    var n = Number(score) || 0;
    return n > 0 ? "+" + Math.trunc(n) : String(Math.trunc(n));
  }

  function alertTs(item) {
    return String((item && (item.asOfIso || item.as_of || item.createdAt)) || "");
  }

  function isBannerFresh(item) {
    var ts = alertTs(item);
    if (!ts || !BANNER_CUTOFF_ISO) return false;
    var t = Date.parse(ts);
    var c = Date.parse(BANNER_CUTOFF_ISO);
    if (isNaN(t) || isNaN(c)) return false;
    return t > c;
  }

  function bannerItems(items) {
    return (Array.isArray(items) ? items : []).filter(function (item) {
      return item && item.id && isBannerFresh(item);
    });
  }

  function itemHtml(item) {
    var score = Number(item.score) || 0;
    var ticker = escapeHtml(item.ticker || "?");
    var gist = escapeHtml(item.gist || "");
    var readThrough = Array.isArray(item.readThrough) ? item.readThrough : [];
    if (readThrough.length) gist += " · thru " + escapeHtml(readThrough.join(", "));
    var inner = '<span class="pb-sym">' + ticker + '</span>'
      + '<span class="pb-score ' + (score > 0 ? "pos" : "neg") + '">' + escapeHtml(fmtScore(score)) + '</span>'
      + '<span class="pb-gist">' + gist + '</span>'
      + '<span class="pb-time">' + escapeHtml(item.asOfPt || "") + '</span>';
    var id = escapeHtml(item.id || "");
    var link = String(item.link || "");
    if (/^https?:\/\//i.test(link)) {
      return '<a class="pb-item" data-peanut-id="' + id + '" href="' + escapeHtml(link) + '" target="_blank" rel="noopener">' + inner + '</a>';
    }
    return '<span class="pb-item" data-peanut-id="' + id + '">' + inner + '</span>';
  }

  function labelHtml() {
    return '<div class="pb-label"><span class="dot"></span><span class="pb-name">Peanut news</span>'
      + '<button class="pb-sound" type="button" aria-pressed="' + (soundOn ? "true" : "false")
      + '" aria-label="Peanut alert sound" title="Peanut alert sound">' + (soundOn ? "🔊" : "🔇") + '</button></div>';
  }

  function renderBanner(items) {
    var valid = bannerItems(items);
    var track = valid.map(itemHtml).join("");
    banner.innerHTML = labelHtml() + (track
      ? '<div class="pb-track"><div class="pb-marquee">' + track + '<span class="pb-item" aria-hidden="true">·</span>' + track + '</div></div>'
      : '<div class="pb-empty">No new alerts since prior RTH close · <a class="pb-arch" href="news-archive.html">News Archive</a></div>');
    var button = banner.querySelector(".pb-sound");
    if (button) button.addEventListener("click", toggleSound);
  }

  function ensureAudio() {
    if (!audioContext) {
      var AudioCtor = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtor) return null;
      try { audioContext = new AudioCtor(); } catch (_) { return null; }
    }
    if (audioContext.state === "suspended") {
      try { audioContext.resume(); } catch (_) {}
    }
    return audioContext;
  }

  function playChime(score) {
    if (!soundOn || document.hidden) return;
    var ctx = ensureAudio();
    if (!ctx) return;
    var start = ctx.currentTime + 0.01;
    var bullish = Number(score) >= 0;
    var first = bullish ? 660 : 440;
    var second = bullish ? 880 : 330;
    [first, second].forEach(function (frequency, index) {
      var at = start + index * 0.16;
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(frequency, at);
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.075, at + 0.018);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.14);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(at);
      osc.stop(at + 0.15);
    });
  }

  function toggleSound() {
    soundOn = !soundOn;
    try { localStorage.setItem(SOUND_KEY, soundOn ? "on" : "off"); } catch (_) {}
    if (soundOn) {
      ensureAudio(); // User gesture unlocks the Web Audio context where allowed.
    }
    var button = banner.querySelector(".pb-sound");
    if (button) {
      button.setAttribute("aria-pressed", soundOn ? "true" : "false");
      button.textContent = soundOn ? "🔊" : "🔇";
    }
  }

  function processItems(items, initial) {
    var all = Array.isArray(items) ? items.filter(function (item) { return item && item.id; }) : [];
    var valid = bannerItems(all);
    var fresh = [];
    valid.forEach(function (item) {
      var id = String(item.id);
      if (!seen.has(id)) {
        seen.add(id);
        if (!initial) fresh.push(item);
      }
    });
    // Acknowledge archive-only ids too so a later cutoff shift does not chime old news.
    all.forEach(function (item) {
      var id = String(item.id);
      if (id) seen.add(id);
    });
    saveSeen();
    if (fresh.length) {
      renderBanner(all);
      if (soundOn) fresh.forEach(function (item, index) {
        window.setTimeout(function () { playChime(item.score); }, index * 420);
      });
    }
  }

  function poll() {
    if (document.hidden || pollBusy) return;
    pollBusy = true;
    fetch("peanut-news.json?t=" + Date.now(), { cache: "no-store" })
      .then(function (response) { if (!response.ok) throw new Error("news fetch " + response.status); return response.json(); })
      .then(function (data) { processItems(data && data.items, false); })
      .catch(function () {})
      .finally(function () { pollBusy = false; });
  }

  readSeen();
  var firstVisit = false;
  try { firstVisit = !localStorage.getItem(SEEDED_KEY); } catch (_) { firstVisit = seen.size === 0; }
  if (firstVisit) {
    seedFromBanner(); // Existing published items are silently acknowledged on first visit.
    try { localStorage.setItem(SEEDED_KEY, "1"); } catch (_) {}
  } else {
    saveSeen();
  }
  try { soundOn = localStorage.getItem(SOUND_KEY) === "on"; } catch (_) { soundOn = false; }
  var initialButton = banner.querySelector(".pb-sound");
  if (initialButton) {
    initialButton.setAttribute("aria-pressed", soundOn ? "true" : "false");
    initialButton.textContent = soundOn ? "🔊" : "🔇";
    initialButton.addEventListener("click", toggleSound);
  }
  window.setInterval(poll, POLL_MS);
  poll();
}());
"""

BANNER_CSS = f"""
.peanut-banner{{position:fixed;left:0;right:0;bottom:0;z-index:80;height:36px;display:flex;align-items:stretch;border-top:1px solid #2a3a50;background:linear-gradient(180deg,#0f1722,#0a1018);box-shadow:0 -8px 24px rgba(0,0,0,.35)}}
.peanut-banner .pb-label{{flex:0 0 auto;display:flex;align-items:center;gap:6px;padding:0 12px;font-size:.72rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#9ecbff;border-right:1px solid #1a2533;background:#0c121a}}
.peanut-banner .pb-label .dot{{width:7px;height:7px;border-radius:50%;background:#4da3ff;box-shadow:0 0 8px #4da3ff;animation:blink 1.6s infinite}}
.peanut-banner .pb-sound{{width:22px;height:22px;margin-left:2px;padding:0;border:1px solid #2a4a70;border-radius:5px;background:#152030;color:#cfe5ff;font-size:.82rem;line-height:20px;cursor:pointer}}
.peanut-banner .pb-sound:hover,.peanut-banner .pb-sound:focus-visible{{background:#1d3550;color:#fff;outline:1px solid #74b7ff;outline-offset:1px}}
.peanut-banner .pb-sound[aria-pressed="true"]{{border-color:#4da3ff;color:#fff}}
.peanut-banner .pb-track{{flex:1 1 auto;overflow:hidden;mask-image:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent);-webkit-mask-image:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent)}}
.peanut-banner .pb-marquee{{display:inline-flex;align-items:center;gap:28px;white-space:nowrap;padding-left:100%;animation:peanut-scroll {MARQUEE_DURATION_S}s linear infinite;will-change:transform}}
.peanut-banner:hover .pb-marquee{{animation-play-state:paused}}
@keyframes peanut-scroll{{0%{{transform:translateX(0)}}100%{{transform:translateX(-100%)}}}}
.peanut-banner .pb-item{{display:inline-flex;align-items:center;gap:8px;font-size:.78rem;color:var(--text)}}
.peanut-banner .pb-sym{{font-weight:750;letter-spacing:.04em}}
.peanut-banner .pb-score{{font-family:var(--mono);font-weight:700;font-variant-numeric:tabular-nums;padding:1px 6px;border-radius:999px;font-size:.72rem}}
.peanut-banner .pb-score.pos{{background:#123526;color:var(--good);border:1px solid #1e5c40}}
.peanut-banner .pb-score.neg{{background:#3a1518;color:var(--bad);border:1px solid #6a2830}}
.peanut-banner .pb-gist{{color:#c5d2e3;max-width:520px;overflow:hidden;text-overflow:ellipsis}}
.peanut-banner .pb-time{{color:var(--muted);font-size:.68rem;font-family:var(--mono)}}
.peanut-banner a.pb-item{{text-decoration:none;color:inherit}}
.peanut-banner a.pb-item:hover .pb-gist{{color:#fff}}
.peanut-banner .pb-empty{{padding:0 14px;color:var(--muted);font-size:.78rem;display:flex;align-items:center;gap:6px}}
.peanut-banner a.pb-arch{{color:#9ecbff;text-decoration:none}}
.peanut-banner a.pb-arch:hover{{color:#fff;text-decoration:underline}}
body{{padding-bottom:44px}}
"""


def _now_pt() -> datetime:
    return datetime.now(PT)


def _parse_alert_dt(item: dict[str, Any]) -> Optional[datetime]:
    """Parse alert timestamp (prefer asOfIso)."""
    raw = item.get("asOfIso") or item.get("as_of") or item.get("createdAt")
    if not raw:
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        s = str(raw).strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PT)
    return dt


def fmt_cutoff_pt(cutoff: Optional[datetime] = None) -> str:
    cutoff = cutoff or prior_rth_close()
    pt = cutoff.astimezone(PT)
    return pt.strftime("%Y-%m-%d %-I:%M %p PT")


def split_banner_archive(
    items: list[dict[str, Any]] | None = None,
    *,
    when: Optional[datetime] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], datetime]:
    """Split store items into (banner, archive_all, prior_rth_close).

    Banner = alerts with timestamp strictly after the prior completed RTH close.
    Archive list is the full history (newest first); nothing is deleted from the store.
    """
    data_items = items
    if data_items is None:
        data_items = [i for i in (load_store().get("items") or []) if isinstance(i, dict)]
    cutoff = prior_rth_close(when)
    banner: list[dict[str, Any]] = []
    archive: list[dict[str, Any]] = []
    for it in data_items:
        if not isinstance(it, dict):
            continue
        archive.append(it)
        ts = _parse_alert_dt(it)
        if ts is not None and ts > cutoff:
            banner.append(it)
    return banner, archive, cutoff


def load_store() -> dict[str, Any]:
    if STORE.exists():
        try:
            data = json.loads(STORE.read_text())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {
        "version": 1,
        "source": "Peanut · News Alerts",
        "mandate": "Research / alerts only · zero RH orders",
        "updatedAt": None,
        "items": [],
    }


def save_store(data: dict[str, Any]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    data = dict(data)
    data["updatedAt"] = _now_pt().strftime("%Y-%m-%d %I:%M %p PT").lstrip("0").replace(" 0", " ")
    data["as_of"] = _now_pt().isoformat()
    data["as_of_pt"] = data["updatedAt"]
    data["writer"] = "Peanut"
    text = json.dumps(data, indent=2) + "\n"
    STORE.write_text(text)
    DASHBOARD_COPY.write_text(text)
    latest = root.parent / "market-data" / "latest" / "peanut-news.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(text)


def fmt_score(score: int | float) -> str:
    s = int(score)
    if s > 0:
        return f"+{s}"
    return str(s)


def append_alert(
    *,
    ticker: str,
    score: int,
    gist: str,
    link: str | None = None,
    why: str | None = None,
    read_through: list[str] | None = None,
    alert_id: str | None = None,
) -> dict[str, Any]:
    """Append or refresh one move-worthy Peanut alert. Dedupes by alert_id or ticker+link."""
    data = load_store()
    items: list[dict] = list(data.get("items") or [])
    ticker_u = ticker.strip().upper()
    score_i = max(-5, min(5, int(score)))
    if score_i == 0:
        score_i = 1
    aid = alert_id or f"{ticker_u}:{link or gist[:48]}"
    now = _now_pt()
    stamp = now.strftime("%I:%M %p PT").lstrip("0")
    entry = {
        "id": aid,
        "ticker": ticker_u,
        "score": score_i,
        "gist": gist.strip(),
        "link": (link or "").strip() or None,
        "why": (why or "").strip() or None,
        "readThrough": [x.upper() for x in (read_through or [])],
        "asOfPt": stamp,
        "asOfIso": now.isoformat(),
    }
    items = [i for i in items if i.get("id") != aid]
    items.insert(0, entry)
    data["items"] = items[:MAX_ITEMS]
    save_store(data)
    return entry


def _item_chunk(it: dict[str, Any]) -> str:
    ticker = html.escape(str(it.get("ticker") or "?"))
    score = int(it.get("score") or 0)
    score_cls = "pos" if score > 0 else "neg"
    score_txt = html.escape(fmt_score(score))
    gist = html.escape(str(it.get("gist") or ""))
    when = html.escape(str(it.get("asOfPt") or ""))
    rt = it.get("readThrough") or []
    if rt:
        gist = f"{gist} · thru {html.escape(', '.join(str(x) for x in rt))}"
    inner = (
        f'<span class="pb-sym">{ticker}</span>'
        f'<span class="pb-score {score_cls}">{score_txt}</span>'
        f'<span class="pb-gist">{gist}</span>'
        f'<span class="pb-time">{when}</span>'
    )
    link = it.get("link")
    aid = html.escape(str(it.get("id") or ""))
    if link:
        return (
            f'<a class="pb-item" data-peanut-id="{aid}" href="{html.escape(str(link))}" '
            f'target="_blank" rel="noopener">{inner}</a>'
        )
    return f'<span class="pb-item" data-peanut-id="{aid}">{inner}</span>'


def render_banner_html() -> tuple[str, str]:
    """Return (html, css). Banner shows only net-new alerts since prior RTH close."""
    banner_items, _archive, cutoff = split_banner_archive()
    label = (
        '<div class="pb-label"><span class="dot"></span><span class="pb-name">Peanut news</span>'
        '<button class="pb-sound" type="button" aria-pressed="false" '
        'aria-label="Peanut alert sound" title="Peanut alert sound">🔇</button></div>'
    )
    if not banner_items:
        html_out = (
            '<div class="peanut-banner" aria-label="Peanut news alerts">'
            f"{label}"
            '<div class="pb-empty">No new alerts since prior RTH close · '
            '<a class="pb-arch" href="news-archive.html">News Archive</a></div>'
            "</div>"
        )
        return html_out, BANNER_CSS

    chunks = [_item_chunk(it) for it in banner_items]
    track = "".join(chunks)
    html_out = (
        '<div class="peanut-banner" aria-label="Peanut news alerts" '
        f'data-banner-cutoff="{html.escape(cutoff.isoformat())}">'
        f"{label}"
        '<div class="pb-track"><div class="pb-marquee">'
        f'{track}<span class="pb-item" aria-hidden="true">·</span>{track}'
        "</div></div></div>"
    )
    return html_out, BANNER_CSS


def render_banner_js() -> str:
    """Return browser-side polling / seen-ID / Web Audio JS with live RTH cutoff."""
    cutoff = prior_rth_close()
    return BANNER_JS.replace("__BANNER_CUTOFF_ISO__", cutoff.isoformat())


def build_news_archive_html(tab_nav: str, *, now_pt: str | None = None) -> str:
    """Full Peanut news history page (archive + still-live banner items)."""
    now_pt = now_pt or _now_pt().strftime("%Y-%m-%d %-I:%M %p PT")
    banner_items, archive, cutoff = split_banner_archive()
    banner_ids = {str(i.get("id")) for i in banner_items if i.get("id")}
    cutoff_pt = fmt_cutoff_pt(cutoff)
    data = load_store()
    updated = html.escape(str(data.get("updatedAt") or data.get("as_of_pt") or "—"))

    rows: list[str] = []
    for it in archive:
        aid = str(it.get("id") or "")
        live = aid in banner_ids
        score = int(it.get("score") or 0)
        score_cls = "pos" if score > 0 else "neg"
        score_txt = html.escape(fmt_score(score))
        ticker = html.escape(str(it.get("ticker") or "?"))
        gist = html.escape(str(it.get("gist") or ""))
        rt = it.get("readThrough") or []
        if rt:
            gist = f"{gist} <span class='rt'>· thru {html.escape(', '.join(str(x) for x in rt))}</span>"
        why = html.escape(str(it.get("why") or ""))
        ts = _parse_alert_dt(it)
        if ts is not None:
            when_pt = ts.astimezone(PT).strftime("%Y-%m-%d %-I:%M %p PT")
        else:
            when_pt = str(it.get("asOfPt") or "—")
        link = it.get("link")
        if link:
            link_html = (
                f'<a href="{html.escape(str(link))}" target="_blank" rel="noopener">source</a>'
            )
        else:
            link_html = "—"
        badge = (
            '<span class="tchip live">banner</span>'
            if live
            else '<span class="tchip arch">archive</span>'
        )
        why_cell = why if why else "—"
        rows.append(
            "<tr>"
            f"<td class='num'>{html.escape(when_pt)}</td>"
            f"<td class='num'>{ticker}</td>"
            f"<td class='num'><span class='score {score_cls}'>{score_txt}</span></td>"
            f"<td class='gist'>{gist}</td>"
            f"<td class='notes'>{why_cell}</td>"
            f"<td>{link_html}</td>"
            f"<td>{badge}</td>"
            "</tr>"
        )
    tbody = "\n".join(rows) or "<tr><td colspan='7' class='empty'>No Peanut alerts stored yet.</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta http-equiv="refresh" content="120"/>
<title>OID · News Archive</title>
<style>
:root{{
  --bg:#070b10; --panel:#0e141c; --line:#1a2533;
  --text:#e8eef7; --muted:#7f91a8; --accent:#4da3ff;
  --good:#3dd68c; --bad:#ff6b7a; --warn:#f0b429;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:Inter,system-ui,-apple-system,sans-serif;background:
  radial-gradient(900px 420px at 8% -8%,#142033 0%,transparent 55%),
  radial-gradient(700px 380px at 100% 0%,#1a1528 0%,transparent 50%),
  var(--bg);color:var(--text);min-height:100vh}}
.wrap{{max-width:1340px;margin:0 auto;padding:22px 18px 56px}}
h1{{font-size:1.35rem;margin:0 0 6px}}
.sub{{color:var(--muted);font-size:.88rem;line-height:1.45}}
.tabs{{display:flex;gap:8px;margin:0 0 16px;flex-wrap:wrap}}
.tabs a{{display:inline-block;padding:7px 14px;border-radius:999px;border:1px solid var(--line);color:var(--muted);text-decoration:none;font-size:.78rem;font-weight:650;letter-spacing:.04em;text-transform:uppercase}}
.tabs a.active,.tabs a:hover{{color:var(--text);border-color:#2a4a70;background:#152030}}
.callout{{margin:14px 0;padding:12px 14px;border:1px solid #2a4a70;border-radius:12px;background:#121a24;color:#c5d2e3;font-size:.88rem;line-height:1.45}}
.table-wrap{{border:1px solid var(--line);border-radius:12px;overflow:auto;background:var(--panel)}}
table{{width:100%;border-collapse:collapse;min-width:960px}}
th,td{{padding:9px 11px;text-align:left;font-size:.84rem;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:600;font-size:.68rem;text-transform:uppercase;background:#0a1018;position:sticky;top:0}}
td.num{{font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}}
td.gist{{color:#c5d2e3;line-height:1.4;max-width:420px}}
td.notes,.empty,.rt{{font-size:.78rem;color:var(--muted);line-height:1.35}}
.score{{font-family:var(--mono);font-weight:700;padding:1px 7px;border-radius:999px;font-size:.78rem}}
.score.pos{{background:#123526;color:var(--good);border:1px solid #1e5c40}}
.score.neg{{background:#3a1518;color:var(--bad);border:1px solid #6a2830}}
.tchip{{display:inline-block;font-size:.62rem;padding:2px 7px;border-radius:999px;border:1px solid var(--line);letter-spacing:.04em;text-transform:uppercase;font-weight:700}}
.tchip.live{{color:var(--good);border-color:#1e5c40;background:#123526}}
.tchip.arch{{color:var(--muted);background:#0a1018}}
a{{color:var(--accent)}}
footer{{margin-top:20px;color:var(--muted);font-size:.8rem;line-height:1.45}}
code{{font-size:.8em;background:#0a1018;padding:1px 5px;border-radius:4px}}
</style>
</head><body><div class="wrap">
{tab_nav}
<h1>News Archive · Peanut</h1>
<div class="sub">Full history from <code>peanut-news.json</code> · Built {html.escape(now_pt)} · Store updated {updated}</div>
<div class="callout">
Live banner shows only alerts <strong>after</strong> the prior completed RTH close
(<strong>{html.escape(cutoff_pt)}</strong>).
Currently <strong>{len(banner_items)}</strong> on banner · <strong>{len(archive)}</strong> in archive.
Older alerts stay in the store; they leave the marquee after each RTH close.
Soft / research only — zero RH orders.
</div>
<div class="table-wrap"><table>
<thead><tr>
  <th>Time (PT)</th><th>Ticker</th><th>Score</th><th>Gist</th><th>Why</th><th>Link</th><th>Status</th>
</tr></thead>
<tbody>
{tbody}
</tbody></table></div>
<footer>
Peanut · News Alerts · Owner of the bottom marquee on the Blotter.
Prior RTH close = previous weekday regular-session cash close (normally 1:00 PM PT / 4:00 PM ET; early-close days honored).
</footer>
</div></body></html>
"""


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Append Peanut news alert or print banner")
    ap.add_argument("--ticker")
    ap.add_argument("--score", type=int)
    ap.add_argument("--gist")
    ap.add_argument("--link")
    ap.add_argument("--why")
    ap.add_argument("--id")
    ap.add_argument("--read-through", nargs="*", default=[])
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--split", action="store_true", help="Print banner/archive counts + cutoff")
    args = ap.parse_args()
    if args.split:
        banner, archive, cutoff = split_banner_archive()
        print(json.dumps({
            "priorRthCloseEt": cutoff.isoformat(),
            "priorRthClosePt": fmt_cutoff_pt(cutoff),
            "bannerCount": len(banner),
            "archiveCount": len(archive),
            "bannerIds": [i.get("id") for i in banner],
            "marqueeDurationS": MARQUEE_DURATION_S,
        }, indent=2))
    elif args.render:
        h, _ = render_banner_html()
        print(h)
    elif args.ticker and args.score is not None and args.gist:
        print(json.dumps(append_alert(
            ticker=args.ticker,
            score=args.score,
            gist=args.gist,
            link=args.link,
            why=args.why,
            read_through=args.read_through,
            alert_id=args.id,
        ), indent=2))
    else:
        ap.error("need --ticker --score --gist, or --render / --split")
