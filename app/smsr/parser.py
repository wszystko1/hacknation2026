"""Parser of a commune page of SMSR IUNG (https://susza.iung.pulawy.pl/wykazy/{year},{TERYT7}/).

The page holds five tables: symbols for soil categories I-IV (crop x 14 periods) and the share of the commune's
area at risk (crop x 14 periods, all soil categories together). Standard library only: the pages are regular.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

SYMBOLS = {"+", "-", "x", "#", "*", "n"}
SOIL_CATEGORIES = ("I", "II", "III", "IV")

# Pages of some years list fruit trees and bushes in one row.
ALIASES: dict[str, tuple[str, ...]] = {
    "Drzewa owocowe": ("Drzewa i krzewy owocowe",),
    "Krzewy owocowe": ("Drzewa i krzewy owocowe",),
}


class SmsrPageError(ValueError):
    """The page is not a commune table of SMSR (wrong address, maintenance page, changed layout)."""


@dataclass
class CommuneTable:
    teryt: str
    commune: str
    year: int
    cells: dict[tuple[str, str, int], str] = field(default_factory=dict)  # (crop, soil, period) -> symbol
    shares: dict[tuple[str, int], float | None] = field(default_factory=dict)  # (crop, period) -> %
    periods: dict[int, tuple[str, str]] = field(default_factory=dict)  # period -> (start, end) ISO dates

    def crops(self) -> list[str]:
        return sorted({crop for crop, _, _ in self.cells})

    def _crop(self, label: str, known: set[str]) -> str | None:
        if label in known:
            return label
        return next((alias for alias in ALIASES.get(label, ()) if alias in known), None)

    def symbol(self, crop_label: str, soil: str, period: int) -> str | None:
        """The symbol of the cell ("+", "-", "x", "#", "*", "n"); None when the page has no such cell."""
        crop = self._crop(crop_label, {c for c, _, _ in self.cells})
        return self.cells.get((crop, soil, period)) if crop else None

    def area_share_pct(self, crop_label: str, period: int) -> float | None:
        """Share of the commune's area at risk of drought in %; None for "x" / "n" and missing cells."""
        crop = self._crop(crop_label, {c for c, _ in self.shares})
        return self.shares.get((crop, period)) if crop else None


class _Tables(HTMLParser):
    """Collects the headings, the commune title and the rows of the `tab-gmina` tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.tables: list[tuple[str, list[tuple[str, str]], list[list[str]]]] = []
        self._heading = ""
        self._tag = ""  # "h5", "h6", "th", "td" while inside such a tag
        self._text: list[str] = []
        self._title_attr = ""
        self._in_table = False
        self._head: list[tuple[str, str]] = []
        self._rows: list[list[str]] = []
        self._row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "h5" and "card-title" in classes:
            self._tag, self._text = "h5", []
        elif tag == "h6":
            self._tag, self._text = "h6", []
        elif tag == "table" and "tab-gmina" in classes:
            self._in_table, self._head, self._rows = True, [], []
        elif self._in_table and tag == "tr":
            self._row = []
        elif self._in_table and tag in {"th", "td"}:
            self._tag, self._text = tag, []
            self._title_attr = a.get("title") or ""

    def handle_data(self, data: str) -> None:
        if self._tag:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        text = " ".join("".join(self._text).split())
        if tag == "h5" and self._tag == "h5":
            self.title, self._tag = text, ""
        elif tag == "h6" and self._tag == "h6":
            self._heading, self._tag = text, ""
        elif tag in {"th", "td"} and self._tag == tag:
            if tag == "th":
                self._head.append((text, self._title_attr))
            else:
                self._row.append(text)
            self._tag = ""
        elif tag == "tr" and self._in_table and self._row:
            self._rows.append(self._row)
            self._row = []
        elif tag == "table" and self._in_table:
            self._in_table = False
            self.tables.append((self._heading, self._head, self._rows))


def parse_commune_page(html: str) -> CommuneTable:
    """Read the symbols (14 crops x 14 periods x 4 soil categories) and the area shares of one commune page."""
    reader = _Tables()
    reader.feed(html)
    title = re.search(r"Gmina:\s*(.+?)\s*;\s*TERYT:\s*(\d{7})", reader.title)
    if not title or not reader.tables:
        raise SmsrPageError("the page has no commune title or no SMSR tables")
    teryt = title.group(2)
    table = CommuneTable(teryt=teryt, commune=title.group(1), year=0)
    for heading, head, rows in reader.tables:
        periods = [(int(text), span) for text, span in head[1:] if text.isdigit()]
        if not table.year and periods:
            table.year = int(periods[0][1][:4])
        soil_match = re.match(r"Kategoria gleby (I{1,3}|IV)$", heading)
        if soil_match is None and not heading.startswith("Udział powierzchni"):
            continue
        for row in rows:
            crop, values = row[0], row[1:]
            for (period, span), value in zip(periods, values, strict=False):
                table.periods.setdefault(period, (span[:10], span[-10:]))
                if soil_match:
                    table.cells[(crop, soil_match.group(1), period)] = value
                else:
                    table.shares[(crop, period)] = _share(value)
    if not table.year or not table.cells:
        raise SmsrPageError("the SMSR tables are empty")
    return table


def _share(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
