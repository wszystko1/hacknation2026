"""Rotation-group agreement with the JRC map, on two hand-made parcels (no data/raw, no network)."""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

from app.geodata import SceneIndex

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("eval_rotation", ROOT / "scripts" / "eval_rotation.py")
eval_rotation = importlib.util.module_from_spec(_spec)
sys.modules["eval_rotation"] = eval_rotation
_spec.loader.exec_module(eval_rotation)


def season(year: int, curve: list[tuple[str, float]]) -> list[SceneIndex]:
    return [SceneIndex(f"s{i}", f"{year}-{d}", 0, 0.0, v, 0.2, 1.0, 100) for i, (d, v) in enumerate(curve)]


# Winter crop: green in March, peak in May, harvested in July -> "ozime".
WINTER = [("03-15", 0.55), ("04-20", 0.7), ("05-25", 0.85), ("06-25", 0.7), ("07-10", 0.25), ("08-20", 0.2)]
# Spring crop: bare in March-April, green by mid-May, peak in June -> "jare".
SPRING = [("03-15", 0.15), ("04-20", 0.2), ("05-15", 0.45), ("06-20", 0.8), ("07-25", 0.6), ("08-30", 0.2)]


def test_dictionary_gives_every_class_one_group_or_a_reason() -> None:
    with eval_rotation.DICTIONARY.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    codes = [int(r["code"]) for r in rows]
    assert len(codes) == len(set(codes))
    for row in rows:
        assert row["group"] in {*eval_rotation.GROUPS, "skip"}
        assert row["reason"].strip()
    from app.geodata.crop_hint import LEGEND

    assert set(LEGEND) <= set(codes)  # every class of the map is covered
    assert eval_rotation.read_dictionary()[211] == "ozime"


def test_two_parcels_give_the_agreement_worked_out_by_hand() -> None:
    dictionary = eval_rotation.read_dictionary()
    parcels = {
        "a": {2018: {211: 90, 213: 10}},  # wheat -> ozime
        "b": {2018: {215: 50, 500: 50}, 2022: {300: 100}},  # half oats, half grass: mixed; forest: skipped
    }
    seasons = {"a": {2018: season(2018, WINTER)}, "b": {2018: season(2018, SPRING)}}
    result, confusion = eval_rotation.compare(parcels, seasons, dictionary)
    assert result == {"crop.rotation_n": 1, "crop.rotation_agreement_jrc": 1.0}
    assert confusion[("ozime", "ozime")] == 1

    parcels["b"] = {2018: {215: 100}}  # oats -> jare, while the satellite curve below is a winter crop
    seasons["b"] = {2018: season(2018, WINTER)}
    result, confusion = eval_rotation.compare(parcels, seasons, dictionary)
    assert result == {"crop.rotation_n": 2, "crop.rotation_agreement_jrc": 0.5}
    assert confusion[("jare", "ozime")] == 1


def test_no_comparable_season_gives_no_numbers(tmp_path) -> None:
    result, confusion = eval_rotation.compare({"a": {2018: {100: 10}}}, {}, eval_rotation.read_dictionary())
    assert result == {} and not confusion
    eval_rotation.write_confusion(confusion, tmp_path / "m.csv")
    assert (tmp_path / "m.csv").read_text(encoding="utf-8").startswith("mapa_JRC")
