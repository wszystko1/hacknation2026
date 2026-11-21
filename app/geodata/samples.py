"""Small committed samples (real downloads, frozen) so the app and tests work without network or cache."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import config
from .models import SOURCE_TYPES, FetchResult, Ortho, SourceResult, from_dict


def sample_stem(parcel_id: str, day: str) -> str:
    return re.sub(r"[^0-9A-Za-z]+", "_", parcel_id).strip("_") + "__" + day


def save_sample(result: FetchResult, directory: Path | None = None) -> Path:
    """Write the result as <stem>.json plus <stem>.jpg (orthophoto) into demo/data/geodata."""
    directory = directory or config.demo_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stem = sample_stem(result.parcel_id, result.date)
    payload = result.to_dict()
    if result.ortho.usable:
        (directory / f"{stem}.jpg").write_bytes(result.ortho.data.image)
    path = directory / f"{stem}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def list_samples(directory: Path | None = None) -> list[tuple[str, str]]:
    """(parcel_id, date) of every committed sample."""
    directory = directory or config.demo_dir()
    found = []
    for path in sorted(directory.glob("*__*.json")):
        head = json.loads(path.read_text(encoding="utf-8"))
        found.append((head["parcel_id"], head["date"]))
    return found


def _source(name: str, raw: dict[str, Any], image: bytes | None) -> SourceResult[Any]:
    data = raw.get("data")
    if data is not None:
        if name == "ortho":
            data = Ortho(**(data | {"image": image or b""}))
        else:
            data = from_dict(SOURCE_TYPES[name], data)
    return SourceResult(**(raw | {"data": data}))


def load_sample(parcel_id: str, day: str, directory: Path | None = None) -> FetchResult | None:
    """The frozen result for a sample parcel and date, or None. Every source gets the note "demo sample"."""
    directory = directory or config.demo_dir()
    path = directory / f"{sample_stem(parcel_id, day)}.json"
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    image_path = path.with_suffix(".jpg")
    image = image_path.read_bytes() if image_path.is_file() else None
    sources = {}
    for name in SOURCE_TYPES:
        missing = {"source": name, "status": "skipped", "notes": ["not in this sample"]}
        sources[name] = _source(name, raw.get(name) or missing, image)
        sources[name].from_cache = True
        sources[name].notes = [*sources[name].notes, "demo sample: frozen copy of a real download"]
    return FetchResult(
        parcel_id=raw["parcel_id"], date=raw["date"], total_ms=0, budget_s=raw["budget_s"], **sources
    )
