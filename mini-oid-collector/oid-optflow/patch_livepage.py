#!/usr/bin/env python3
"""Idempotent patch: add Alpaca-OPRA aggressor chips (15s C/P, 1m C/P) to livepage.py + index.html.
Usage: patch_livepage.py <dir-with-livepage.py-and-index.html>   (re-run safe; marker 'OPTFLOW')"""
import sys, re
from pathlib import Path
d = Path(sys.argv[1])
lp, ix = d / "livepage.py", d / "index.html"
s = lp.read_text(); h = ix.read_text()

def rep(src, old, new, label):
    if old not in src:
        raise SystemExit(f"anchor missing: {label}")
    return src.replace(old, new, 1)

if "OPTFLOW" not in s:
    s = rep(s, 'SECTORS_FILE = HERE / "sectors.json"',
            'SECTORS_FILE = HERE / "sectors.json"\n'
            'OPTFLOW_FILE = Path(os.environ.get("OID_LIVEPAGE_OPTFLOW", str(Path.home() / "oid-optflow/data/optflow.json")))  # OPTFLOW: Alpaca OPRA aggressor flow\n'
            'OPTFLOW_STALE_S = 30.0  # no trade for this long (RTH) -> chip greyed\n', "SECTORS_FILE")
    s = rep(s, "    def build(self):\n        now = time.time()\n",
            "    def optflow(self, now):\n"
            "        \"\"\"OPTFLOW: read ~/oid-optflow/data/optflow.json (written every 1 s by com.oid.desk.optflow).\"\"\"\n"
            "        try:\n"
            "            d = json.loads(OPTFLOW_FILE.read_text())\n"
            "        except Exception:\n"
            "            return {}, None\n"
            "        age = now - float(d.get(\"computed_epoch\") or 0)\n"
            "        meta = {\"computed_at\": d.get(\"computed_at\"), \"age_s\": round(age, 2), \"ws\": (d.get(\"ws\") or {}).get(\"state\"),\n"
            "                \"subs\": d.get(\"subs\"), \"lag\": d.get(\"exch_to_recv_lag_5m\"), \"source\": d.get(\"source\")}\n"
            "        return (d.get(\"underlyings\") or {}) if age < 10 else {}, meta\n\n"
            "    def build(self):\n        now = time.time()\n", "build")
    s = rep(s, '            r["uw"] = bool(u)  # True when this symbol is in core-20/focus UW set\n',
            '            r["uw"] = bool(u)  # True when this symbol is in core-20/focus UW set\n'
            '            a = of_rows.get(r["sym"])  # OPTFLOW\n'
            '            if a:\n'
            '                def _c(w):\n'
            '                    w = a.get(w) or {}\n'
            '                    return {"cp": w.get("cp_buy"), "net_k": round((w.get("net") or 0) / 1000, 1), "cov": w.get("coverage"),\n'
            '                            "n": w.get("n"), "thin": bool(w.get("thin", True)), "cb_k": round((w.get("cb") or 0) / 1000, 1),\n'
            '                            "pb_k": round((w.get("pb") or 0) / 1000, 1)}\n'
            '                r["af15"], r["af60"] = _c("15s"), _c("60s")\n'
            '                lr = a.get("last_recv")\n'
            '                try:\n'
            '                    r["af_age"] = round(now - datetime.fromisoformat(lr).timestamp(), 1) if lr else None\n'
            '                except Exception:\n'
            '                    r["af_age"] = None\n'
            '                r["af_stale"] = bool(rth and (r["af_age"] is None or r["af_age"] > OPTFLOW_STALE_S))\n'
            '                r["af_n"] = a.get("contracts")\n'
            '            else:\n'
            '                r["af15"] = r["af60"] = r["af_age"] = r["af_n"] = None\n'
            '                r["af_stale"] = True\n', "uw flag")
    s = rep(s, "        for r in rows:\n            r[\"hot\"] =",
            "        of_rows, of_meta = self.optflow(now)  # OPTFLOW\n        for r in rows:\n            r[\"hot\"] =", "rows loop")
    s = rep(s, '"rows": rows, "options": opts,', '"rows": rows, "optflow": of_meta, "options": opts,', "payload")
    s = rep(s, '"cp", "lean15", "net15_m", "ask_lean", "uw",', '"cp", "lean15", "net15_m", "ask_lean", "uw", "af15", "af60", "af_age", "af_stale", "af_n",', "LIGHT_KEYS")
    lp.write_text(s)

if "OPTFLOW" not in h:
    h = rep(h, ".tile .chip.flat{color:var(--amber);border-color:#9a670066}",
            ".tile .chip.flat{color:var(--amber);border-color:#9a670066}\n"
            "/* OPTFLOW chips: Alpaca OPRA aggressor flow (live) */\n"
            ".tile .chip.af{border-style:solid;border-width:1px 1px 1px 3px}.tile .chip.dim{opacity:.4}.tile .chip.slow{opacity:.75;font-style:italic}", "css")
    h = rep(h, "function leanBadge(r){if(!r.uw)return '';\n const bits=[];\n",
            "function afCls(c){return c==null?'':c>=1.25?'call':c<=0.8?'put':'flat';}\n"
            "function afChip(r,lab,w){/* OPTFLOW */ if(!w)return '';const dim=r.af_stale||w.thin||w.cp==null;\n"
            " const cov=w.cov==null?'':Math.round(w.cov*100)+'%';const v=w.cp==null?'—':(w.cp>=99?'∞':(+w.cp).toFixed(1));\n"
            " const t=`${lab} aggressor flow (Alpaca OPRA, live): call-buy $${w.cb_k}K vs put-buy $${w.pb_k}K · net ${w.net_k>0?'+':''}${w.net_k}K · ${w.n} prints · classified ${cov} of premium · ${r.af_n||0} contracts streamed`+(r.af_age!=null?` · last print ${r.af_age}s ago`:'')+(dim?' · GREY = thin (<5 prints) or stale (>30s)':'');\n"
            " return `<span class=\"chip af ${dim?'dim':afCls(w.cp)}\" title=\"${t}\">${lab} C/P ${v}<sup>${cov}</sup></span>`;}\n"
            "function leanBadge(r){if(!r.uw&&!r.af15)return '';\n const bits=[];\n"
            " bits.push(afChip(r,'15s',r.af15));bits.push(afChip(r,'1m',r.af60));\n", "leanBadge")
    h = rep(h, " if(r.lean15)bits.push(`<span class=\"chip ${leanCls(r.lean15)}\">15m ${E(r.lean15)}</span>`);\n bits.push(lean5Chip(r));",
            " if(r.lean15)bits.push(`<span class=\"chip slow ${leanCls(r.lean15)}\" title=\"UW 15m net call−put (slow: UW file refresh ~4 min)\">15m ${E(r.lean15)}</span>`);\n if(r.uw)bits.push(lean5Chip(r));", "15m chip")
    h = rep(h, " return bits.length?", " return bits.filter(Boolean).length?", "bits filter")
    h = h.replace("bits.join('')}</div>`:'';}", "bits.filter(Boolean).join('')}</div>`:'';}", 1)
    h = rep(h, "tile chip = day C/P vol + 15m and 5m call−put lean",
            "tile chips = <b>15s / 1m C/P = live Alpaca OPRA aggressor call-buy÷put-buy premium (small % = classified coverage; grey = thin/stale)</b> + day C/P vol + 15m (slow, italic) and 5m call−put lean", "legend")
    ix.write_text(h)
print("patched", d)
