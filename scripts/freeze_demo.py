"""Rebuild the offline copies of the two demo parcels: uv run python scripts/freeze_demo.py

Needs the IMGW station index in data/raw/imgw (`uv run python -m app.geodata imgw-sync` builds it) and the
network. Refuses to write when a season misses more than 5% of its weather days.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.geodata.freeze import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
