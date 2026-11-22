"""Freeze the data of several parcels for the location tests: uv run python scripts/freeze_locations.py [name ...]

Needs the network once and the IMGW station index (`uv run python -m app.geodata imgw-sync`). For every location it
writes demo/data/locations/<name>/ with the same layout the app reads from demo/data:

    geodata/    outline, weather, terrain, soil, ditches, satellite indices, forecast, orthophoto
    soil/       IUNG soil map reading
    satellite/  Sentinel-2 season history
    smsr/       the IUNG commune page of the year

A location that cannot be frozen (a source does not answer, too many weather gaps) is reported and skipped, so
the tests only ever see complete copies. tests/test_locations.py reads them without a network.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crop_condition import background  # noqa: E402
from app.geodata import fetch_parcel_by_lonlat, load_sample
from app.geodata.freeze import FreezeRefused, Target, freeze  # noqa: E402
from app.geodata.parcel import normalize_parcel_id  # noqa: E402
from app.geodata.samples import sample_stem  # noqa: E402
from app.smsr import pages  # noqa: E402
from app.soil import iung  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "demo" / "data" / "locations"
TODAY = date.today()


@dataclass(frozen=True)
class Location:
    name: str
    voivodeship: str
    day: date
    crop: str
    parcel_id: str = ""  # empty: found from the coordinates
    lon: float = 0.0
    lat: float = 0.0


CANDIDATES = (
    Location("dobrcz", "kujawsko-pomorskie", date(2023, 7, 20), "zboza_jare", "040303_2.0002.189/13"),
    Location("gora-sw-malgorzaty", "łódzkie", TODAY, "rosliny_straczkowe", "100403_2.0011.144"),
    Location("kietrz", "opolskie", date(2022, 7, 20), "rzepak", "160204_5.0001.101"),
    Location("podkarpackie-podgorze", "podkarpackie", date(2021, 5, 4), "zboza_jare", lon=22.68041, lat=50.08863),
    Location("malopolska-wyzyna", "małopolskie", date(2020, 6, 4), "zboza_ozime", lon=20.20762, lat=50.34384),
    Location("lubuskie-poza-sezonem", "lubuskie", TODAY, "drzewa_owocowe", lon=15.81010, lat=52.13909),
    Location("lubelskie-susza", "lubelskie", date(2022, 7, 30), "kukurydza_ziarno", lon=23.45486, lat=50.75629),
    Location("pomorskie-rzepak", "pomorskie", date(2024, 8, 1), "rzepak", lon=19.15560, lat=54.06869),
    Location("zachodniopomorskie", "zachodniopomorskie", date(2023, 5, 21), "ziemniak", lon=14.82101, lat=53.23106),
    Location("podlaskie-chmiel", "podlaskie", date(2023, 4, 27), "chmiel", lon=22.45396, lat=52.80917),
    Location("slaskie-poza-sezonem", "śląskie", TODAY, "kukurydza_ziarno", lon=18.44838, lat=50.02004),
    Location("dolnoslaskie-tyton", "dolnośląskie", date(2019, 6, 11), "tyton", lon=16.68941, lat=51.22183),
)  # fmt: skip


def _resolve(loc: Location) -> str:
    if loc.parcel_id:
        return normalize_parcel_id(loc.parcel_id)
    found = fetch_parcel_by_lonlat(loc.lon, loc.lat)
    if not found.usable:
        raise FreezeRefused(f"no parcel at {loc.lon},{loc.lat}: {found.error}")
    return found.data.id


def _freeze_satellite(parcel_id: str, day: date, target: Path) -> None:
    sample = load_sample(parcel_id, day.isoformat(), target.parent / "geodata")
    assert sample is not None
    seasons = background.compute(sample.parcel.data, day, time.monotonic() + 240)
    if not any(seasons.values()):
        print("  satellite history: no readings, left out")
        return
    target.mkdir(parents=True, exist_ok=True)
    body = {
        "parcel_id": parcel_id,
        "date": day.isoformat(),
        "downloaded": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "Sentinel-2 L2A, Microsoft Planetary Computer (STAC)",
        "seasons": background.encode(seasons),
    }
    (target / f"{parcel_id.replace('/', '_').replace('.', '_')}.json").write_text(
        json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


def _copy_demo(parcel_id: str, day: date, folder: Path) -> bool:
    """The two demo parcels are already frozen in demo/data: reuse those files instead of downloading again."""
    from app.geodata import config

    stem = sample_stem(parcel_id, day.isoformat())
    source = config.demo_dir() / f"{stem}.json"
    if not source.is_file():
        return False
    (folder / "geodata").mkdir(parents=True)
    for path in config.demo_dir().glob(f"{stem}.*"):
        shutil.copy(path, folder / "geodata" / path.name)
    short = iung.stem(parcel_id)
    for kind in ("soil", "satellite"):
        for path in (config.repo_root() / "demo" / "data" / kind).glob(f"{short}.json"):
            (folder / kind).mkdir(exist_ok=True)
            shutil.copy(path, folder / kind / path.name)
    return True


def _freeze_one(loc: Location) -> dict:
    parcel_id = _resolve(loc)
    folder = OUT / loc.name
    shutil.rmtree(folder, ignore_errors=True)
    if _copy_demo(parcel_id, loc.day, folder):
        return _entry(loc, parcel_id)
    freeze((Target(parcel_id, loc.day),), folder / "geodata")
    sample = load_sample(parcel_id, loc.day.isoformat(), folder / "geodata")
    assert sample is not None and sample.parcel.usable
    reading = iung.read_live(parcel_id, sample.parcel.data.rings_4326)
    if reading is not None:
        iung.save_frozen(reading, folder / "soil")
    else:
        print("  IUNG soil layer did not answer, left out")
    _freeze_satellite(parcel_id, loc.day, folder / "satellite")
    return _entry(loc, parcel_id)


def _entry(loc: Location, parcel_id: str) -> dict:
    return {
        "name": loc.name,
        "voivodeship": loc.voivodeship,
        "parcel_id": parcel_id,
        "day": loc.day.isoformat(),
        "crop": loc.crop,
    }


def _freeze_smsr(entries: list[dict]) -> None:
    """Run the report once per location with the commune-page cache pointed at the location folder."""
    from fastapi.testclient import TestClient

    from app.geodata import config
    from app.main import app

    client = TestClient(app)
    for e in entries:
        folder = OUT / e["name"]
        saved = (pages.CACHE_DIR, pages.DEMO_DIR, config.demo_dir, iung.frozen_dir, background.frozen_dir)
        pages.CACHE_DIR = folder / "smsr"
        pages.DEMO_DIR = folder / "smsr"
        config.demo_dir = lambda f=folder: f / "geodata"
        iung.frozen_dir = lambda f=folder: f / "soil"
        background.frozen_dir = lambda f=folder: f / "satellite"
        try:
            url = f"/api/raport?dzialka={e['parcel_id']}&data={e['day']}&uprawa={e['crop']}"
            client.get(url)
        finally:
            pages.CACHE_DIR, pages.DEMO_DIR, config.demo_dir, iung.frozen_dir, background.frozen_dir = saved
        print(f"{e['name']}: SMSR pages {sorted(p.name for p in (folder / 'smsr').glob('*.html'))}")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    wanted = set(sys.argv[1:])
    done: list[dict] = []
    for loc in CANDIDATES:
        if wanted and loc.name not in wanted:
            continue
        started = time.monotonic()
        print(f"== {loc.name} ({loc.voivodeship}, {loc.day})", flush=True)
        try:
            done.append(_freeze_one(loc))
        except FreezeRefused as exc:
            print(f"  refused: {exc}", flush=True)
            shutil.rmtree(OUT / loc.name, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001 - one broken location must not stop the others
            print(f"  failed: {type(exc).__name__}: {exc}", flush=True)
            shutil.rmtree(OUT / loc.name, ignore_errors=True)
        else:
            print(f"  done in {time.monotonic() - started:.0f} s", flush=True)
    _freeze_smsr(done)
    OUT.mkdir(parents=True, exist_ok=True)
    index = OUT / "index.json"
    old = json.loads(index.read_text(encoding="utf-8")) if index.is_file() and wanted else []
    merged = {e["name"]: e for e in [*old, *done]}
    index.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"froze {len(done)} locations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
