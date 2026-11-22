"""The scene read for a date is the clearest of the candidates, not the nearest."""

from __future__ import annotations

from datetime import date

from app.geodata import SceneIndex, satellite


def _index(item: dict, share: float | None) -> SceneIndex:
    return SceneIndex(
        scene_id=item["id"], date=item["date"], days_from_target=0, cloud_cover_pct=5.0,
        ndvi=None if share is None else 0.6, ndmi=0.1, valid_fraction=share or 0.0, pixels=50,
    )  # fmt: skip


def _pick(monkeypatch, shares: list[float | None], **kw):
    items = [{"id": f"s{i}", "date": "2023-07-20"} for i in range(len(shares))]
    by_id = {f"s{i}": s for i, s in enumerate(shares)}
    monkeypatch.setattr(satellite, "scene_index", lambda item, *a: _index(item, by_id[item["id"]]))
    return satellite._best_scene(items, None, date(2023, 7, 20), None, None, **kw)


def test_the_clearest_scene_wins_over_the_nearest(monkeypatch) -> None:
    assert _pick(monkeypatch, [0.19, 0.55, 0.95, 0.7]).scene_id == "s2"


def test_one_clean_scene(monkeypatch) -> None:
    assert _pick(monkeypatch, [0.19, 0.6, 0.3]).scene_id == "s1"


def test_no_scene_reaches_the_threshold_but_the_best_is_returned_for_the_note(monkeypatch) -> None:
    best = _pick(monkeypatch, [0.1, 0.3, 0.2])
    assert best.scene_id == "s1" and best.valid_fraction < satellite.MIN_CLEAR_SHARE


def test_scenes_without_ndvi_are_skipped(monkeypatch) -> None:
    assert _pick(monkeypatch, [None, 0.8]).scene_id == "s1"
