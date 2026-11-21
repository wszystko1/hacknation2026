"""Fetch all data for one parcel: uv run python scripts/fetch_parcel.py 040303_2.0004.121/7 2026-07-15"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.geodata.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["fetch", *sys.argv[1:]]))
