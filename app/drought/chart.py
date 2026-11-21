"""The threshold bar under the verdict number: svg.hbar, viewBox 0 0 600 84 (docs/DESIGN.md)."""

from __future__ import annotations

from app.fmt import dec, svg_text
from app.models import Verdict


def hbar_svg(v: Verdict) -> str:
    """Bar from 0 mm (left) to the scale end (right); the fill is the deficit, the black tick the threshold."""
    if v.kbw_mm is None:
        return ""
    deficit = max(-v.kbw_mm, 0.0)
    thr = -v.threshold_mm if v.threshold_mm is not None else None
    scale = max(deficit, thr or 0.0, 1.0) * 1.15
    x0, width = 20.0, 560.0

    def x(mm: float) -> float:
        return x0 + width * mm / scale

    parts = [f'<rect class="hbar-track" x="{x0}" y="32" width="{width}" height="16" rx="5"/>']
    if thr is not None and deficit > thr:
        parts.append(
            f'<rect class="hbar-fill" x="{x0}" y="32" width="{x(thr) - x0:.1f}" height="16" rx="5"/>'
        )
        parts.append(
            f'<rect class="hbar-over" x="{x(thr):.1f}" y="32" width="{x(deficit) - x(thr):.1f}" height="16"/>'
        )
    else:
        cls = "hbar-fill hbar-fill--ok" if thr is not None else "hbar-fill"
        parts.append(
            f'<rect class="{cls}" x="{x0}" y="32" width="{x(deficit) - x0:.1f}" height="16" rx="5"/>'
        )
    if thr is not None:
        parts.append(f'<rect class="hbar-thr" x="{x(thr) - 1.5:.1f}" y="26" width="3" height="28" rx="1.5"/>')
        parts.append(
            f'<text class="lbl-thr" x="{x(thr):.1f}" y="22" text-anchor="middle">próg {dec(-thr)}</text>'
        )
    parts.append(f'<text x="{x0}" y="78">0 mm</text>')
    parts.append(
        f'<text class="lbl-val" x="{x(deficit):.1f}" y="78" text-anchor="middle">{dec(v.kbw_mm)}</text>'
    )
    label = f"Bilans {dec(v.kbw_mm)} mm" + (
        f" wobec progu {dec(v.threshold_mm)} mm" if thr is not None else ""
    )
    return (
        f'<svg class="hbar" viewBox="0 0 600 84" role="img" aria-label="{svg_text(label)}">'
        f"<title>{svg_text(label)}</title>" + "".join(parts) + "</svg>"
    )
