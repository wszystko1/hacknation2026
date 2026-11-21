"""Fill the cache in data/raw for a list of parcels: uv run python scripts/fetch_prewarm.py demo/data/geodata/demo_parcels.txt"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.geodata.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["prewarm", *sys.argv[1:]]))
