"""Feed catalog (desk config/mirror-feeds.json): which desk-relative files are served / mirrored / accepted."""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any, Optional

from . import util


def load(desk: Optional[Path] = None) -> dict:
    d = desk or util.desk()
    cat = util.read_json(d / "config" / "mirror-feeds.json")
    if not isinstance(cat, dict) or "groups" not in cat:
        raise RuntimeError("config/mirror-feeds.json missing or invalid")
    return cat


def _safe_rel(rel: str) -> bool:
    return bool(rel) and not rel.startswith("/") and ".." not in Path(rel).parts and "\x00" not in rel


def expand(cat: dict, desk: Optional[Path] = None, groups: Optional[list[str]] = None) -> dict[str, str]:
    """-> {desk-relative path: group} for files that currently exist."""
    d = desk or util.desk()
    out: dict[str, str] = {}
    for g, spec in cat["groups"].items():
        if groups and g not in groups:
            continue
        for pat in spec.get("files", []):
            if not _safe_rel(pat):
                continue
            for p in sorted(glob.glob(str(d / pat))):
                pp = Path(p)
                if pp.is_file() and not pp.is_symlink():
                    out[os.path.relpath(p, d)] = g
    return out


def manifest(cat: dict, desk: Optional[Path] = None, groups: Optional[list[str]] = None) -> list[dict[str, Any]]:
    d = desk or util.desk()
    rows = []
    for rel, g in expand(cat, d, groups).items():
        p = d / rel
        try:
            st = p.stat()
            rows.append({"name": rel, "group": g, "size": st.st_size, "mtime": st.st_mtime,
                         "sha256": util.sha256_file(p), "as_of": _as_of(p)})
        except OSError:
            continue
    return rows


def _as_of(p: Path) -> Optional[str]:
    if p.suffix != ".json" or p.stat().st_size > 8_000_000:
        return None
    d = util.read_json(p)
    if isinstance(d, dict):
        for k in ("as_of", "as_of_pt", "generated_pt", "written_epoch", "generated_epoch", "atPT"):
            if d.get(k) is not None:
                return str(d[k])
    return None


def desk_state_allowed(cat: dict, rel: str) -> bool:
    return _safe_rel(rel) and rel in set(cat.get("desk_state", []))
