"""Load ``cache_io`` from ``market-data/`` (that directory name is not a package)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_MARKET = ROOT / "market-data"


def cache_io():
    market = str(_MARKET)
    if market not in sys.path:
        sys.path.insert(0, market)
    import cache_io as module

    return module
