"""Seed ~/oid-data/score/latest.json from the newest slot of a scores file (off-hours / demo). Labels kind."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "oid-score"))
import score_lib as L, score_engine as E
src = Path(sys.argv[1]); kind = sys.argv[2] if len(sys.argv) > 2 else "last_logged"
rows = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
rows = [r for r in rows if r.get("trigger") in ("anchor", "grid")]
tmax = max(r["t"] for r in rows)
by = {r["sym"]: E.summary(r) for r in rows if r["t"] == tmax}
out = {"as_of": tmax, "as_of_pt": L.pt_str(tmax), "config_version": rows[-1]["config_version"], "kind": kind, "by_sym": by, "source_file": src.name}
(L.OUT / "latest.json").write_text(json.dumps(out, separators=(",", ":")))
print("seeded", len(by), "symbols from", src.name, "@", L.pt_str(tmax), "kind", kind)
