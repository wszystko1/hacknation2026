# ruff: noqa
"""Wspólne: ładowanie próbki z data/raw/ponds_matched/data (the repository is not touched)."""

import importlib.util
import os
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[2]  # product root
W = P / "data" / "raw" / "ponds_matched"  # downloaded sample and cache (not in the repository)
os.environ.setdefault("GEODATA_CACHE_DIR", str(W / "cache"))
sys.path.insert(0, str(P))


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, P / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_samples():
    """Jak eval_ponds.load_samples(), ale ze sklepu w data/raw/ponds_matched/data."""
    sample = load_script("fetch_retention_sample")
    ponds_store = load_script("fetch_ponds")
    out = []
    for row in sample.read_rows():
        loaded = sample.load_parcel(row["dzialka"], W / "data" / "retention_sample")
        ponds = ponds_store.load_ponds(row["dzialka"], W / "data" / "ponds")
        if loaded is None or ponds is None:
            continue
        terrain = loaded[1]
        out.append((terrain.catchment_grid or terrain.grid, ponds))
    return out
