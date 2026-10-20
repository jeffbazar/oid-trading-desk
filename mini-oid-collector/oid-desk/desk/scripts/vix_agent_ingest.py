#!/usr/bin/env python3
"""Write market-data/latest/vix-agent.json from ONE agent Robinhood read (pluggable VIX, default source agent_rh).

  python3 scripts/vix_agent_ingest.py --quotes-file rh-index-quotes.json [--historicals-file rh-index-hist.json]
The mirror poller pushes the file to the mini (desk-state) where oid_desk.vix reads it. Research / paper only.
Parsing reuses dashboard/macro_spot.py (_parse_vix_quote / _parse_vix_prev) so both paths agree.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OID = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OID / "dashboard"))
sys.path.insert(0, str(OID / "market-data"))
import cache_io  # noqa: E402
import macro_spot  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quotes-file", type=Path, required=True)
    ap.add_argument("--historicals-file", type=Path)
    a = ap.parse_args(argv)
    val = macro_spot._parse_vix_quote(json.loads(a.quotes_file.read_text()))
    prev = macro_spot._parse_vix_prev(json.loads(a.historicals_file.read_text())) if a.historicals_file else None
    if val is None:
        print("ERROR: no VIX value in quotes file", file=sys.stderr)
        return 1
    rec = cache_io.write_feed("vix-agent", source="robinhood get_index_quotes (agent read)",
                              writer="scripts/vix_agent_ingest.py", symbols=["VIX"],
                              payload={"value": val, "prev_close": prev}, ttl_seconds=5400)
    print(json.dumps({"vix": val, "prev_close": prev, "as_of_pt": rec["as_of_pt"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
