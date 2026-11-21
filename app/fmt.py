"""Polish number and date formatting shared by templates, sentences and charts."""

from __future__ import annotations

from datetime import date
from html import escape

MINUS = "−"


def dec(x: float | None, digits: int = 0) -> str:
    """12,5 / −219 / 21 530 (thin grouping), "–" for None."""
    if x is None:
        return "–"
    text = f"{x:,.{digits}f}".replace(",", " ").replace(".", ",")
    return text.replace("-", MINUS)


def mm(x: float | None) -> str:
    return f"{dec(x)} mm"


def ha(x: float | None) -> str:
    return f"{dec(x, 2)} ha"


def pct(x: float | None, digits: int = 0) -> str:
    return "–" if x is None else f"{dec(100 * x, digits)}%"


def day(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "–"


def day_month(d: date | None) -> str:
    return d.strftime("%d.%m") if d else "–"


def seconds(x: float | None) -> str:
    return "–" if x is None else f"{dec(x, 1)} s"


def svg_text(s: str) -> str:
    return escape(s, quote=True)
