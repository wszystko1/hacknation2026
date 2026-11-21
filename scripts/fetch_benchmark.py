"""Cold and warm timings of the data layer: uv run python scripts/fetch_benchmark.py -n 10"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.geodata.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["benchmark", *sys.argv[1:]]))
