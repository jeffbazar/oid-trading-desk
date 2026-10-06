#!/usr/bin/env python3
"""Rebuild architecture.html and setup.html. Does not publish.

Production publish remains ``dashboard/publish.sh`` on the box, slug
``bold-tulip-nejq``. swift-dune is review-only. Research / paper only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import docs_pages


def rebuild(out_dir, root=None, built_at="2026-10-05 5:43 PM PT") -> dict:
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    architecture = docs_pages.render_architecture(root=root, built_at=built_at)
    setup = docs_pages.render_setup(root=root, built_at=built_at)
    architecture_path = destination / "architecture.html"
    setup_path = destination / "setup.html"
    architecture_path.write_text(architecture, encoding="utf-8")
    setup_path.write_text(setup, encoding="utf-8")
    nav = [href for href, _label in docs_pages.NAV]
    if "architecture.html" not in nav or "setup.html" not in nav:
        raise RuntimeError("blotter nav is missing architecture/setup")
    return {
        "architecture": str(architecture_path),
        "setup": str(setup_path),
        "nav": nav,
        "published": False,
        "execution": "none",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Write architecture.html and setup.html locally.")
    parser.add_argument("--out", default="site")
    parser.add_argument("--root", default=None)
    parser.add_argument("--built-at", default="2026-10-05 5:43 PM PT")
    args = parser.parse_args(argv)
    result = rebuild(args.out, root=args.root, built_at=args.built_at)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
