"""Freeze the season history of the demo parcels: uv run python scripts/freeze_satellite.py [parcel_id date ...]

Needs the network. Writes demo/data/satellite/<parcel>.json: for each parcel the readings of the season of the
given day (up to that day) and of the five seasons before it, so the demo and the tests show the plant
assessment at once and without a network.
"""

import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crop_condition import background  # noqa: E402
from app.geodata import fetch_parcel  # noqa: E402

DEMO = (("040303_2.0002.189/13", "2023-07-20"), ("100403_2.0011.144", "2026-11-21"))


def freeze(parcel_id: str, day: date) -> Path:
    parcel = fetch_parcel(parcel_id).data
    started = time.monotonic()
    seasons = background.compute(parcel, day, started + 1500)
    counts = {y: len(r) for y, r in seasons.items()}
    print(f"{parcel_id}: readings per season {counts} in {time.monotonic() - started:.0f} s")
    if sum(counts.values()) == 0:
        raise SystemExit(f"{parcel_id}: no readings, nothing written")
    path = background.frozen_path(parcel_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "parcel_id": parcel.id,
        "date": day.isoformat(),
        "downloaded": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "Sentinel-2 L2A, Microsoft Planetary Computer (STAC)",
        "seasons": background.encode(seasons),
    }
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def main() -> int:
    args = sys.argv[1:]
    pairs = list(zip(args[::2], args[1::2], strict=False)) or list(DEMO)
    for parcel_id, day in pairs:
        print("written", freeze(parcel_id, date.fromisoformat(day)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
