"""Agreement of the rotation group read from Sentinel-2 with the JRC EUCROPMAP class: `make eval ONLY=rotation`.

For each parcel and season (2018, 2022) from data/raw/jrc_cropmap (written by scripts/fetch_jrc_cropmap.py)
we take the group `classify_season` gives from the season's readings and compare it with the group of the
map class that covers most of the parcel. The class dictionary is demo/data/eval/jrc_classes.csv; classes
marked `skip` (mixed content such as barley, not farmland) leave the season out, as do parcels where no group
covers at least MIN_GROUP_SHARE of the mapped pixels. Writes
  crop.rotation_n                 seasons compared,
  crop.rotation_agreement_jrc     share with the same group (0-1),
and the confusion matrix (rows: map, columns: satellite) to artifacts/rotation_confusion.csv.
Without the downloaded data `run()` returns nothing and metrics.json keeps its values.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.crop_condition import classify_season  # noqa: E402
from app.geodata import SceneIndex  # noqa: E402

DATA = ROOT / "data" / "raw" / "jrc_cropmap"
DICTIONARY = ROOT / "demo" / "data" / "eval" / "jrc_classes.csv"
ARTIFACT = ROOT / "artifacts" / "rotation_confusion.csv"
GROUPS = ["ozime", "jare", "pozne", "tuz", "gola_gleba"]
MIN_GROUP_SHARE = 0.6  # a parcel counts when one group covers this share of its mapped pixels
MIN_SEASONS = 30  # fewer compared seasons is too small a sample to quote


def read_dictionary(path: Path = DICTIONARY) -> dict[int, str]:
    """Map class code -> group, or "skip". Every row must name a group from GROUPS or skip, with a reason."""
    out: dict[int, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["group"] not in {*GROUPS, "skip"} or not row["reason"].strip():
                raise ValueError(f"class {row['code']}: group {row['group']!r} or reason missing")
            out[int(row["code"])] = row["group"]
    return out


def map_group(counts: dict[int, int], dictionary: dict[int, str]) -> str | None:
    """Group of the map for one parcel, or None when the parcel is mixed, unmapped or all skipped."""
    total = sum(counts.values())
    by_group: Counter[str] = Counter()
    for code, n in counts.items():
        group = dictionary.get(code, "skip")
        if group != "skip":
            by_group[group] += n
    if not by_group or total == 0:
        return None
    group, n = by_group.most_common(1)[0]
    return group if n / total >= MIN_GROUP_SHARE else None


def compare(
    parcels: dict[str, dict[int, dict[int, int]]],
    seasons: dict[str, dict[int, list[SceneIndex]]],
    dictionary: dict[int, str],
) -> tuple[dict[str, float | int], Counter[tuple[str, str]]]:
    """Agreement numbers and the confusion counts {(map group, satellite group): n}.

    parcels: parcel -> year -> class code -> pixels; seasons: parcel -> year -> readings.
    """
    confusion: Counter[tuple[str, str]] = Counter()
    for parcel, years in parcels.items():
        for year, counts in years.items():
            expected = map_group(counts, dictionary)
            seen = classify_season(seasons.get(parcel, {}).get(year, []))
            if expected is not None and seen is not None:
                confusion[(expected, seen)] += 1
    n = sum(confusion.values())
    if n == 0:
        return {}, confusion
    same = sum(v for (a, b), v in confusion.items() if a == b)
    return {"crop.rotation_n": n, "crop.rotation_agreement_jrc": round(same / n, 4)}, confusion


def write_confusion(confusion: Counter[tuple[str, str]], path: Path = ARTIFACT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["mapa_JRC \\ satelita", *GROUPS])
        for expected in GROUPS:
            writer.writerow([expected, *(confusion[(expected, seen)] for seen in GROUPS)])


def load(data: Path = DATA) -> tuple[dict, dict]:
    parcels: dict[str, dict[int, dict[int, int]]] = {}
    with (data / "classes.csv").open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            parcels.setdefault(r["parcel"], {}).setdefault(int(r["year"]), {})[int(r["code"])] = int(
                r["pixels"]
            )
    seasons: dict[str, dict[int, list[SceneIndex]]] = {}
    for key in parcels:
        path = data / "seasons" / f"{key}.json"
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            seasons[key] = {int(y): [SceneIndex(**r) for r in rs] for y, rs in raw.items()}
    return parcels, seasons


def run() -> dict[str, float | int]:
    if not (DATA / "classes.csv").is_file():
        print(f"eval rotation: {DATA} missing; run scripts/fetch_jrc_cropmap.py first")
        return {}
    parcels, seasons = load()
    result, confusion = compare(parcels, seasons, read_dictionary())
    if result:
        write_confusion(confusion)
        if result["crop.rotation_n"] < MIN_SEASONS:
            print(f"eval rotation: only {result['crop.rotation_n']} seasons (aim: at least {MIN_SEASONS})")
    return result


if __name__ == "__main__":
    print(run())
