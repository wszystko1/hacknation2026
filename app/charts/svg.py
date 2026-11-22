"""Small helpers for server-built SVG charts (see docs/DESIGN.md, "Charts")."""

from __future__ import annotations

from app.fmt import svg_text

WIDTH = 600


def svg(height: int, label: str, body: list[str], desc: str = "", title: str = "") -> str:
    """<svg class="ch"> with <title>/<desc>; `body` is a list of SVG elements built with the helpers below."""
    chart = (
        f'<svg class="ch" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{svg_text(label)}">'
        f"<title>{svg_text(label)}</title><desc>{svg_text(desc or label)}</desc>" + "".join(body) + "</svg>"
    )
    if not title:
        return chart
    # the chart title is HTML above the drawing, never text inside it
    return f'<div class="chart-title">{svg_text(title)}</div>{chart}'


def rect(x: float, y: float, w: float, h: float, cls: str) -> str:
    return f'<rect class="{cls}" x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{max(h, 0):.1f}"/>'


def line(x1: float, y1: float, x2: float, y2: float, cls: str) -> str:
    return f'<line class="{cls}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"/>'


def polyline(points: list[tuple[float, float]], cls: str) -> str:
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline class="{cls}" points="{pts}"/>'


def text(x: float, y: float, s: str, cls: str = "", anchor: str = "start") -> str:
    c = f' class="{cls}"' if cls else ""
    return f'<text{c} x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}">{svg_text(s)}</text>'
