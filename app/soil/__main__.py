"""`python -m app.soil freeze`: read the IUNG layer for the demo parcels and store the readings in demo/data/soil/."""

from __future__ import annotations

import sys

from app.geodata import list_samples, load_sample

from . import iung


def freeze() -> int:
    done: set[str] = set()
    status = 0
    for parcel_id, day in list_samples():
        if parcel_id in done:
            continue
        done.add(parcel_id)
        sample = load_sample(parcel_id, day)
        if sample is None or not sample.parcel.usable:
            continue
        reading = iung.read_live(parcel_id, sample.parcel.data.rings_4326)
        if reading is None:
            print(f"{parcel_id}: the IUNG layer did not answer")
            status = 1
            continue
        print(iung.save_frozen(reading), reading.counts, iung.classify(reading).category)
    return status


if __name__ == "__main__":
    sys.exit(freeze() if sys.argv[1:] == ["freeze"] else print(__doc__) or 2)
