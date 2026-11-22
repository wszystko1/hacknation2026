"""Jedna komenda: jakość ocen, przyczyn i rad na jednej stronie.

  uv run python scripts/jakosc.py                    # tabela liczb z metrics.json + złote lokalizacje offline (ok. 30 s)
  uv run python scripts/jakosc.py --online ADRES     # złote lokalizacje na działającej aplikacji (ADRES, np. https://…)
  uv run python scripts/jakosc.py --przelicz         # przelicza pomiary (make eval; wymaga sieci, kilka minut)
  uv run python scripts/jakosc.py --szybko           # tylko tabela liczb

Tabela mówi, co każda liczba oznacza i czego nie dowodzi (te same zastrzeżenia, co w README).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def get(m: dict, path: str):
    cur = m
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def pct(v, d=1) -> str:
    return "brak" if v is None else f"{100 * v:.{d}f}%"


def num(v, d=2) -> str:
    return "brak" if v is None else f"{v:.{d}f}"


def rows(m: dict) -> list[tuple[str, str, str, str]]:
    g = lambda p: get(m, p)  # noqa: E731
    cal = g("smsr.confirm_share_margin_le_minus25")
    return [
        (
            "WERDYKT",
            "Zgodność z oceną państwa (SMSR), bilans ≥ 25 mm pod progiem",
            pct(cal),
            "na gminach (149 gmin, 1017 gmino-lat), nie pomiar w polu",
        ),
        (
            "WERDYKT",
            "Zgodność przy marginesie 0–10 mm / 10–25 mm od progu",
            f"{pct((g('smsr.agreement_by_distance') or {}).get('0–10 mm'))} / {pct((g('smsr.agreement_by_distance') or {}).get('10–25 mm'))}",
            "przy samym progu rzut monetą; raport mówi to wprost",
        ),
        (
            "WERDYKT",
            "CSI (D–G, werdykt) / (FAO-56) / klimatologia",
            f"{num(g('smsr.csi_dg'))} / {num(g('smsr.csi_fao56'))} / "
            f"{num(g('smsr.baseline_csi_climatology'))}",
            "CSI: trafienia wobec trafień, fałszywych alarmów i pominięć; susza to 4,5% symboli",
        ),
        (
            "WERDYKT",
            "Czułość (POD) D–G / FAO-56; precyzja alarmów",
            f"{num(g('smsr.pod_dg'))} / {num(g('smsr.pod_fao56'))}; {num(g('smsr.precision_dg'))}",
            "metoda wskazuje ok. połowę susz SMSR; alarmy potwierdzają się w ok. 4 na 5",
        ),
        (
            "PROGNOZA",
            "BSS prognozy przekroczenia progu (wobec częstości historycznej)",
            num(g("forecast.brier_skill")),
            "0 = bez umiejętności, 1 = idealna",
        ),
        (
            "GLEBA",
            "Zapas SoilGrids: dokładna zgodność / w granicach jednej kategorii",
            f"{pct(g('soil.category_agreement'))} / {pct(g('soil.agreement_within_one'))}",
            f"{g('soil.n_points')} punktów; dotyczy zapasu, nie mapy IUNG",
        ),
        (
            "RETENCJA",
            "Najniższy punkt granicy do 30 m od rowu / losowy punkt",
            f"{pct(g('retention.outlet_hit_lowest'), 0)} / {pct(g('retention.outlet_hit_random'), 0)}",
            "optymistyczne: rów jest zagłębieniem w modelu terenu",
        ),
        (
            "RETENCJA",
            "Niecka wobec rzeczywistych miejsc zbierania wody",
            "nie zmierzono",
            "brak mapy niecek na polach; miejsca to kandydatury do sprawdzenia w terenie",
        ),
        (
            "RETENCJA",
            "Zastawki wobec rzeczywistych budowli",
            "nie zmierzono",
            "brak otwartych danych o zastawkach rolniczych (pilot BDOT10k: nierozstrzygający)",
        ),
        (
            "SZYBKOŚĆ",
            "Czas raportu: mediana / p95; udział poniżej 30 s",
            f"{num(g('robustness.p50_s'), 1)} s / {num(g('robustness.p95_s'), 1)} s; {pct(g('robustness.report_ok_under_30s_share'), 0)}",
            f"{g('robustness.n_parcels')} działek, {g('robustness.n_voivodeships')} województw, zimny start",
        ),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--online", metavar="ADRES", help="złote lokalizacje na działającej aplikacji")
    ap.add_argument("--przelicz", action="store_true", help="przelicz pomiary (make eval)")
    ap.add_argument("--szybko", action="store_true", help="tylko tabela liczb")
    a = ap.parse_args()
    py = sys.executable
    if a.przelicz:
        print("== Przeliczanie pomiarów (sieć, kilka minut) ==", flush=True)
        subprocess.run([py, "scripts/evaluate.py"], cwd=ROOT, check=False)
    m = json.loads((ROOT / "metrics.json").read_text(encoding="utf-8"))
    print("\n== Jakość: liczby (metrics.json) ==")
    w = max(len(r[1]) for r in rows(m))
    for grp, what, val, note in rows(m):
        print(f"{grp:9} {what:{w}}  {val:>22}  {note}")
    if a.szybko:
        return 0
    env = dict(os.environ, GOLDEN="1")
    if a.online:
        print(f"\n== Złote lokalizacje na żywo: {a.online} ==", flush=True)
        return subprocess.run(["bash", "scripts/golden_check.sh", a.online], cwd=ROOT, env=env).returncode
    print(
        "\n== Złote lokalizacje (offline, zamrożone dane): ręcznie dobrane działki z oczekiwaniami eksperckimi ==",
        flush=True,
    )
    r = subprocess.run(
        [py, "-m", "pytest", "tests/golden", "-q", "--no-header", "-p", "no:cacheprovider"], cwd=ROOT, env=env
    )
    print(
        "\nPASS = oczekiwanie spełnione; XFAIL = znana wada z opisem w tests/golden/expectations.json (known_defects)."
    )
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
