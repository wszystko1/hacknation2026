"""Freeze the daily mean temperature and sunshine of the demo parcels next to the committed weather copies.

The weather copies in demo/data/geodata carry precipitation and ET0 only. The second evaporation variant needs
temperature and sunshine, which the IMGW station index holds (`python -m app.geodata imgw-sync` builds it into
data/raw/imgw). One file per demo copy goes to demo/data/weather_inputs/, from the same synoptic station chain
the live fetch uses. Run: `uv run python scripts/freeze_weather_inputs.py`.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.drought.variants import WEATHER_INPUTS, inputs_file
from app.geodata import imgw
from app.geodata.freeze import DEMO_TARGETS
from app.geodata.samples import load_sample

MAX_SYNOP_KM = 80.0


def freeze(parcel_id: str, day: date) -> Path | None:
    result = load_sample(parcel_id, day.isoformat())
    if result is None or not result.weather.usable:
        print(f"no weather copy for {parcel_id} {day}", file=sys.stderr)
        return None
    w = result.weather.data
    first, last = date.fromisoformat(w.dates[0]), date.fromisoformat(w.dates[-1])
    tmean = imgw.lookup("tmean", w.latitude, w.longitude, first, last, max_km=MAX_SYNOP_KM, max_stations=2)
    sun = imgw.lookup("sun", w.latitude, w.longitude, first, last, max_km=MAX_SYNOP_KM, max_stations=2)
    if tmean is None or sun is None:
        print("IMGW index without temperature and sunshine: rebuild it with imgw-sync", file=sys.stderr)
        return None
    path = inputs_file(parcel_id, day.isoformat())
    WEATHER_INPUTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "parcel_id": parcel_id,
        "day": day.isoformat(),
        "latitude": w.latitude,
        "longitude": w.longitude,
        "source": "IMGW-PIB, dane publiczne, stacje synoptyczne (dobowa temperatura średnia i usłonecznienie)",
        "stations": tmean["stations"],
        "dates": w.dates,
        "tmean_c": tmean["values"],
        "sunshine_h": sun["values"],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    done = [freeze(t.parcel_id, t.day) for t in DEMO_TARGETS]
    for path in done:
        if path:
            print(path)
    return 0 if all(done) else 1


if __name__ == "__main__":
    raise SystemExit(main())
