#!/bin/bash
# Copy docs/live-page into guide/docs (served at /guide/) and write guide/docs/index.json (nav order + titles).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; SRC="$HERE/../../docs/live-page"; DST="$HERE/guide/docs"
rm -rf "$DST"; mkdir -p "$DST/img"
cp "$SRC"/*.md "$DST/"; cp "$SRC"/img/*.png "$DST/img/"
python3 - "$DST" <<'PY'
import sys,json,pathlib,re
d=pathlib.Path(sys.argv[1]);out=[]
files=sorted(p.name for p in d.glob("*.md"))
files=["README.md"]+[f for f in files if f!="README.md"]
for f in files:
    t=next((l[2:].strip() for l in (d/f).read_text().splitlines() if l.startswith("# ")),f)
    if f=="README.md": t="Overview"
    out.append({"file":f,"title":t})
(d/"index.json").write_text(json.dumps(out,indent=1))
print(len(out),"pages")
PY
