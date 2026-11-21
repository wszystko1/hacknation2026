from app.crop_condition import read_together
from app.models import CropCondition


def ok(signal: str | None, **extra: object) -> CropCondition:
    return CropCondition.model_validate({"state": "ok", "words": "rośliny", "signal": signal, "n_seasons": 4} | extra)


def test_four_readings_are_distinct() -> None:
    out = {(v, s): read_together(v, ok(s)) for v in ("below", "above") for s in ("weaker", "normal")}
    assert len(set(out.values())) == 4


def test_no_badge_no_reading() -> None:
    for state in ("running", "no_threshold", "out_of_season", "no_data"):
        assert read_together(state, ok("weaker")) == ""


def test_lagging_does_not_reassure() -> None:
    s = read_together("below", ok("normal")).lower()
    assert not any(w in s for w in ("brak oznak", "nie ma suszy", "w normie"))


def test_missing_picture_states_the_gap() -> None:
    c = CropCondition(state="missing", words="Brak: zdjęcia bez chmur", reason="x")
    assert "brak" in read_together("above", c).lower()


def test_harvest_is_not_read_as_stress() -> None:
    c = ok(None, harvest=True, words="zdjęcie po pokosie: nie ocenia stresu")
    assert "nie ocenia stresu" in read_together("below", c)
