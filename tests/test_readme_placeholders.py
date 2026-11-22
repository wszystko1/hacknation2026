"""The README must not contain unfilled placeholders."""

from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"


def test_readme_has_no_placeholders() -> None:
    text = README.read_text(encoding="utf-8")
    for placeholder in ("NAZWA_ZESPOŁU", "ADRES_DEMO", "ADRES_FILMU"):
        assert placeholder not in text


def test_readme_has_demo_address_and_team() -> None:
    text = README.read_text(encoding="utf-8")
    assert "https://70-34-247-151.sslip.io" in text
    assert "Freesolo" in text
