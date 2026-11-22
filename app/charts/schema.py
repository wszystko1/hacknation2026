""""Jak liczymy": four boxes joined by arrows, data -> balance -> threshold -> verdict. Static, no numbers."""

from __future__ import annotations

from app.charts import svg

HEIGHT = 152
BOX_W, GAP, TOP, BOX_H = 132, 24, 8, 134
STEPS = (
    ("Dane", ("pogoda,", "gleba, uprawa")),
    ("Bilans", ("opad minus", "parowanie")),
    ("Próg", ("tabela z", "rozporządzenia")),
    ("Werdykt", ("bilans poniżej", "progu: susza")),
)


def _icon(i: int, cx: float, cy: float) -> str:
    """A 28 px outline icon centred on (cx, cy); paths only, so no text box ever meets a rect."""
    x, y = cx - 14, cy - 14
    shapes = (
        # data: three stacked layers
        f"M{x:.1f} {y + 8:.1f}l14 -7l14 7l-14 7z M{x:.1f} {y + 15:.1f}l14 7l14 -7 M{x:.1f} {y + 22:.1f}l14 7l14 -7",
        # balance: a drop over a minus
        f"M{cx:.1f} {y:.1f}l9 14a9 9 0 1 1 -18 0z M{cx - 6:.1f} {cy + 6:.1f}h12",
        # threshold: a dashed line under a curve
        f"M{x:.1f} {y + 4:.1f}l9 6l9 -2l10 14 M{x:.1f} {y + 22:.1f}h28",
        # verdict: a tick
        f"M{x:.1f} {cy:.1f}l10 10l18 -20",
    )
    return f'<path class="ic" d="{shapes[i]}"/>'


def schema_svg() -> str:
    body = []
    for i, (title, lines) in enumerate(STEPS):
        x = 2 + i * (BOX_W + GAP)
        cx = x + BOX_W / 2
        body.append(
            f'<path class="box" d="M{x} {TOP}h{BOX_W}v{BOX_H}h-{BOX_W}z"/>'
        )
        body.append(_icon(i, cx, TOP + 28))
        body.append(svg.text(cx, TOP + 70, title, "lbl", "middle"))
        body.append(svg.text(cx, TOP + 96, lines[0], "", "middle"))
        body.append(svg.text(cx, TOP + 122, lines[1], "", "middle"))
        if i < 3:
            ax = x + BOX_W + 4
            ay = TOP + BOX_H / 2
            body.append(f'<path class="ic" d="M{ax} {ay - 8}l12 8l-12 8"/>')
    label = "Jak liczymy: dane, bilans wody, próg z rozporządzenia, werdykt"
    return svg.svg(HEIGHT, label, body, desc=label, title="Cztery kroki oceny")
