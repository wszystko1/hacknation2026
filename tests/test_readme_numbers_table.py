"""README: the numbers chapter states what was measured, what was measured but is weak and what was not measured."""

import re
from pathlib import Path

README = Path("README.md").read_text(encoding="utf-8")
HEADINGS = [line for line in README.splitlines() if line.startswith("#")]


def test_three_state_table_and_not_measured_line_above_it() -> None:
    table_at = README.index("| Stan | Co |")
    line_at = README.index("Czego nie zmierzyliśmy")
    assert line_at < table_at
    table = README[table_at : README.index("\n\n", table_at)]
    for state in ("| zmierzone |", "| zmierzone, słabe |", "| nie zmierzone |"):
        assert state in table


def test_no_accuracy_headline() -> None:
    for heading in HEADINGS:
        assert not re.search(r"96,8\s*%\s*(wobec|vs)", heading)
    assert "96,8% wobec 95,5%" not in README


def test_limits_name_wfs_and_commune_level_agreement() -> None:
    limits = README[README.index("## Uczciwe ograniczenia") :]
    assert "EGiB WFS" in limits and "sali" in limits
    assert "na gminach, nie na działkach" in limits
