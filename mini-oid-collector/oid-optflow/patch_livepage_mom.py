#!/usr/bin/env python3
"""Idempotent patch: C/P momentum arrows (OPTMOM) on the 15s/1m aggressor chips. Needs the OPTFLOW patch first.
Usage: patch_livepage_mom.py <dir-with-livepage.py-and-index.html>   (re-run safe; marker 'OPTMOM')"""
import sys
from pathlib import Path
d = Path(sys.argv[1])
lp, ix = d / "livepage.py", d / "index.html"
s = lp.read_text(); h = ix.read_text()

def rep(src, old, new, label):
    if old not in src:
        raise SystemExit(f"anchor missing: {label}")
    return src.replace(old, new, 1)

if "OPTMOM" not in s:
    s = rep(s, '                r["af15"], r["af60"] = _c("15s"), _c("60s")\n',
            '                r["af15"], r["af60"] = _c("15s"), _c("60s")\n'
            '                _mo = a.get("mom") or {}  # OPTMOM: momentum from optflow 15 s slots\n'
            '                for _k, _w in (("af15", "15s"), ("af60", "60s")):\n'
            '                    _m = _mo.get(_w)\n'
            '                    if _m:\n'
            '                        r[_k].update({"md": _m.get("d"), "ms": _m.get("s"), "mh": _m.get("h"), "mrr": bool(_m.get("rr"))})\n',
            "af15 assign")
    lp.write_text(s)

if "OPTMOM" not in h:
    h = rep(h, ".tile .chip.af{border-style:solid;border-width:1px 1px 1px 3px}",
            ".tile .chip.af{border-style:solid;border-width:1px 1px 1px 3px}"
            "/* OPTMOM */.tile .chip .mo{font-size:8px;margin-left:1px}.tile .chip .mo.u{color:var(--green)}.tile .chip .mo.d{color:var(--red)}.tile .chip .mo.f{color:var(--mut)}", "css")
    h = rep(h, "function afChip(r,lab,w){/* OPTFLOW */",
            "function afMo(w,dim){/* OPTMOM */ if(dim||!w||w.md==null)return '';return w.md>0?'<span class=\"mo u\">▲</span>':w.md<0?'<span class=\"mo d\">▼</span>':'<span class=\"mo f\">–</span>';}\n"
            "function afMoT(w){if(!w||!w.mh)return '';const hs=w.mh.map(x=>x==null?'—':(x>=99?'∞':(+x).toFixed(2))).join(' · ');\n"
            " const dir=w.md==null?'no arrow (needs 3 valid readings incl. latest)':w.md>0?'▲ rising toward calls':w.md<0?'▼ falling toward puts':'– flat';\n"
            " return ` · momentum: ${dir}${w.ms!=null?` (${w.ms>0?'+':''}${w.ms}/min log)`:''} · last 90s: ${hs}`+(w.mrr?' · contracts re-ranked':'');}\n"
            "function afChip(r,lab,w){/* OPTFLOW */", "afMo fn")
    h = rep(h, "+(dim?' · GREY = thin (<5 prints) or stale (>30s)':'');\n",
            "+(dim?' · GREY = thin (<5 prints) or stale (>30s)':'')+afMoT(w);\n", "title")
    h = rep(h, "${lab} C/P ${v}<sup>${cov}</sup></span>`;}", "${lab} C/P ${v}${afMo(w,dim)}<sup>${cov}</sup></span>`;}", "chip arrow")
    h = rep(h, "(small % = classified coverage; grey = thin/stale)</b>",
            "(small % = classified coverage; grey = thin/stale; ▲/▼ = trend over ~45 s of 15 s readings: green toward calls, red toward puts, – flat)</b>", "legend")
    ix.write_text(h)
print("patched", d)
