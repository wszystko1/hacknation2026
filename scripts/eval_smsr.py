"""Agreement of the method with SMSR IUNG on the evaluation communes.

Inputs (both fetched once into data/raw by `scripts/fetch_smsr.py` and `scripts/fetch_commune_weather.py`):
the SMSR commune pages 2020-2026 and the weather of each commune centroid. The evaluation needs no network.

Communes of demo/data/eval/gminy.csv marked "dev" (50) are used to compare the two evaporation formulas;
the numbers of the report come from the "test" communes (150), computed once. The threshold shift is chosen on
2020-2025 and checked on 2026, which it never saw. Writes the `smsr.*` keys of metrics.json; the key without a
suffix is the variant of the report (FAO-56), `_dg` is the Doroszewski-Górski variant.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from app.drought.evaporation import etp_dg_daily
from app.drought.thresholds import threshold_mm
from app.smsr.parser import SmsrPageError, parse_commune_page
from app.validation import calibration, measure
from app.validation.agreement import scores

ROOT = Path(__file__).resolve().parents[1]
COMMUNES = ROOT / "demo" / "data" / "eval" / "gminy.csv"
WEATHER_DIR = ROOT / "data" / "raw" / "commune_weather"
SMSR_DIR = ROOT / "data" / "raw" / "smsr"
YEARS = range(2020, 2027)
SHIFT_GRID = [float(x) for x in range(-60, 61)]
SUFFIXED = ("fao56", "dg")
MEASURES = (
    "csi", "pod", "far", "peirce", "base_rate", "accuracy", "balanced_accuracy", "recall", "precision",
    "accuracy_majority",
)  # fmt: skip
TABLE_KEYS = ("hits", "false_alarms", "misses", "correct_negatives")


def _thresholds() -> dict[tuple, float | None]:
    return {
        (crop, soil, n): threshold_mm(crop, soil, n)  # type: ignore[arg-type]
        for crop in measure.CROPS
        for soil in measure.SOILS
        for n in range(1, 15)
    }


def _series(snap: dict) -> dict[str, tuple[list[str], list, list]]:
    """(dates, precipitation, ET0) per variant of one commune snapshot."""
    first = date.fromisoformat(snap["start"])
    dates = [(first + timedelta(days=i)).isoformat() for i in range(snap["n"])]
    out = {"fao56": (dates, snap["precipitation_mm"], snap["et0_mm"])}
    tmean, sun = snap.get("tmean_c") or [], snap.get("sunshine_h") or []
    if tmean and sun:
        out["dg"] = (dates, snap["precipitation_mm"], etp_dg_daily(dates, tmean, sun, snap["grid_lat"]))
    power = snap.get("power")
    if power:
        out["power"] = (dates, power["precipitation_mm"], power["et0_mm"])
    return out


def load_cases(
    communes: list[str], weather_dir: Path = WEATHER_DIR, smsr_dir: Path = SMSR_DIR
) -> tuple[measure.Cases, list[dict]]:
    cases, snaps = measure.Cases(), []
    thresholds = _thresholds()
    for teryt in communes:
        path = weather_dir / f"{teryt}.json"
        if not path.is_file():
            continue
        snap = json.loads(path.read_text(encoding="utf-8"))
        snaps.append(snap)
        series = _series(snap)
        for year in YEARS:
            page = smsr_dir / f"{year}_{teryt}.html"
            if not page.is_file():
                continue
            try:
                table = parse_commune_page(page.read_text(encoding="utf-8"))
            except SmsrPageError:
                continue
            kbw = {v: measure.period_kbw(*s[:1], s[1], s[2], year) for v, s in series.items()}
            kbw.update({v: {} for v in measure.VARIANTS if v not in kbw})
            measure.add_commune_year(cases, table, kbw, thresholds)
    return cases, snaps


def _round(x: float | None) -> float | None:
    return None if x is None or np.isnan(x) else round(float(x), 4)


def _put(out: dict, key: str, value: float | None) -> None:
    value = _round(value)
    if value is not None:
        out[key] = value


def variant_keys(v: measure.View, communes: list[str], variant: str, suffix: str) -> dict:
    out: dict = {}
    table, s = measure.evaluate(v, variant)
    for name in TABLE_KEYS:
        out[f"smsr.{name}{suffix}"] = getattr(table, name)
    for name in MEASURES:
        _put(out, f"smsr.{name}{suffix}", s[name])
    usable = ~np.isnan(v.margin[variant])
    counts = measure.per_commune_counts(v, v.margin[variant] < 0, usable, communes)
    ci = measure.bootstrap_by_commune(counts, ["csi", "balanced_accuracy", "ratio_below_to_plus"])
    for name, (lo, hi) in ci.items():
        _put(out, f"smsr.{name}_ci_low{suffix}", lo)
        _put(out, f"smsr.{name}_ci_high{suffix}", hi)
    plus = table.hits + table.misses
    if plus:
        _put(out, f"smsr.ratio_below_to_plus{suffix}", (table.hits + table.false_alarms) / plus)
    return out


def baselines(v: measure.View) -> dict:
    ok = ~np.isnan(v.margin["fao56"])
    observed = v.observed[ok]
    out: dict = {"smsr.baseline_csi_never_drought": 0.0}
    always = scores(measure.table_of(np.ones(ok.sum(), dtype=bool), observed))
    clim = scores(measure.table_of(v.clim[ok], observed))
    _put(out, "smsr.baseline_csi_always_drought", always["csi"])
    _put(out, "smsr.baseline_csi_climatology", clim["csi"])
    _put(out, "smsr.baseline_balanced_accuracy_climatology", clim["balanced_accuracy"])
    power_ok = ~np.isnan(v.margin["power"])
    if power_ok.any():
        grid = measure.evaluate(v, "power")[1]
        _put(out, "smsr.baseline_csi_nasa_power_grid", grid["csi"])
        _put(out, "smsr.baseline_balanced_accuracy_nasa_power_grid", grid["balanced_accuracy"])
    return out


def shift_keys(v_all: measure.View, ratio_low: float, ratio_high: float) -> dict:
    """A threshold shift when the interval of the below-to-plus ratio does not contain 1.

    Chosen on 2020-2025 of all communes, checked on 2026; 2026 is not used in the choice.
    """
    if ratio_low <= 1 <= ratio_high:
        return {}
    earlier = v_all.where(v_all.year <= 2025)
    shift = measure.choose_shift(earlier, "fao56", SHIFT_GRID)
    last = v_all.where(v_all.year == 2026)
    if not len(last.year):
        return {}
    out: dict = {"smsr.threshold_shift_mm": shift}
    _put(out, "smsr.balanced_accuracy_2026", measure.evaluate(last, "fao56")[1]["balanced_accuracy"])
    _put(
        out,
        "smsr.balanced_accuracy_2026_shifted",
        measure.evaluate(last, "fao56", shift)[1]["balanced_accuracy"],
    )
    out["smsr.threshold_shift_improves_2026"] = int(
        out.get("smsr.balanced_accuracy_2026_shifted", 0) > out.get("smsr.balanced_accuracy_2026", 0)
    )
    return out


def calibration_keys(v: measure.View, communes: list[str]) -> dict:
    """The "+" share of SMSR by the margin class, both evaporation variants, with 95% intervals by commune."""
    out: dict = {}
    for variant in SUFFIXED:
        margin = v.margin[variant]
        counts = calibration.class_counts(margin, v.observed)
        per_commune = calibration.per_commune_class_counts(margin, v.observed, v.commune, communes)
        intervals = calibration.bootstrap_plus_share(per_commune)
        for cls, (n, _plus), share, ci in zip(
            calibration.CLASSES, counts.tolist(), calibration.plus_share(counts), intervals, strict=True
        ):
            base = f"smsr.calibration.{variant}.{cls.key}"
            out[f"{base}.n"] = int(n)
            _put(out, f"{base}.plus_share", share)
            if ci is not None:
                _put(out, f"{base}.ci_low", ci[0])
                _put(out, f"{base}.ci_high", ci[1])
    # the scalar of the report: the variant of the report (FAO-56), margin of -25 mm and below
    counts = calibration.class_counts(v.margin["fao56"], v.observed)
    share, n = calibration.confirm_share(counts)
    _put(out, "smsr.confirm_share_margin_le_minus25", share)
    out["smsr.confirm_n_margin_le_minus25"] = n
    per_commune = calibration.per_commune_class_counts(v.margin["fao56"], v.observed, v.commune, communes)
    pooled = per_commune[:, :2, :].sum(axis=1)  # (communes, 2): symbols, "+"
    rng = np.random.default_rng(2026)
    draw = rng.integers(0, len(communes), size=(2000, len(communes)))
    sums = pooled[draw].sum(axis=1)
    ok = sums[:, 0] > 0
    if ok.any():
        lo, hi = np.percentile(sums[ok, 1] / sums[ok, 0], [2.5, 97.5])
        _put(out, "smsr.confirm_share_margin_le_minus25_ci_low", lo)
        _put(out, "smsr.confirm_share_margin_le_minus25_ci_high", hi)
    return out


def by_year_keys(v: measure.View, communes: list[str]) -> dict:
    """CSI and the number of "+" symbols per year (variant of the report), CSI interval by commune."""
    out: dict = {}
    for year in YEARS:
        sub = v.where(v.year == year)
        usable = ~np.isnan(sub.margin["fao56"])
        if not usable.any():
            continue
        table, s = measure.evaluate(sub, "fao56")
        base = f"smsr.by_year.{year}"
        out[f"{base}.n"] = int(usable.sum())
        out[f"{base}.plus_count"] = int(sub.observed[usable].sum())
        _put(out, f"{base}.csi", s["csi"])
        counts = measure.per_commune_counts(sub, sub.margin["fao56"] < 0, usable, communes)
        ci = measure.bootstrap_by_commune(counts, ["csi"])["csi"]
        _put(out, f"{base}.csi_ci_low", ci[0])
        _put(out, f"{base}.csi_ci_high", ci[1])
    return out


def weather_shares(snaps: list[dict]) -> dict:
    out: dict = {}
    for kind, field in (("precipitation", "precipitation_sources"), ("et0", "et0_sources")):
        total: dict[str, float] = {}
        for s in snaps:
            for name, share in (s.get(field) or {}).items():
                total[name] = total.get(name, 0.0) + share / len(snaps)
        for name, share in total.items():
            out[f"smsr.weather_share_{kind}_{re.sub(r'[^a-z0-9]+', '_', name)}"] = round(share, 4)
    return out


def run() -> dict[str, float | int]:
    with COMMUNES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    groups = {name: [r["teryt"] for r in rows if r["zbior"] == name] for name in ("dev", "test")}
    cases, snaps = load_cases([r["teryt"] for r in rows])
    if not len(cases):
        return {}
    v = measure.view(cases)
    in_test = np.isin(v.commune, groups["test"])
    test, dev = v.where(in_test), v.where(np.isin(v.commune, groups["dev"]))
    test_communes = sorted(set(v.commune[in_test].tolist()))
    if not test_communes:
        return {}

    out: dict = {}
    for variant in SUFFIXED:
        out.update(variant_keys(test, test_communes, variant, f"_{variant}"))
    out.update({k[: -len("_fao56")]: val for k, val in out.items() if k.endswith("_fao56")})

    ok = ~np.isnan(test.margin["fao56"])
    out["smsr.n_symbols"] = int(ok.sum())
    out["smsr.n_gmina_years"] = len({(c, y) for c, y in zip(test.commune[ok], test.year[ok], strict=True)})
    out["smsr.n_communes"] = len({c for c in test.commune[ok]})
    out.update(baselines(test))
    best = max(out["smsr.baseline_csi_always_drought"], out["smsr.baseline_csi_climatology"])
    _put(out, "smsr.csi_gain_vs_baseline", out["smsr.csi"] - best)
    out["smsr.method_beats_climatology"] = int(out["smsr.csi"] > out["smsr.baseline_csi_climatology"])
    for bucket, share in measure.agreement_by_distance(test, "fao56").items():
        _put(out, f"smsr.agreement_by_distance.{bucket}", share)

    out.update(calibration_keys(test, test_communes))
    out.update(by_year_keys(test, test_communes))

    for variant in SUFFIXED:  # the choice of the formula, on the development communes only
        _put(
            out,
            f"smsr.dev_balanced_accuracy_{variant}",
            measure.evaluate(dev, variant)[1]["balanced_accuracy"],
        )
    dev_fao, dev_dg = (out.get(f"smsr.dev_balanced_accuracy_{x}") for x in SUFFIXED)
    if dev_fao is not None and dev_dg is not None:
        out["smsr.dev_dg_better"] = int(dev_dg > dev_fao)

    low, high = out.get("smsr.ratio_below_to_plus_ci_low"), out.get("smsr.ratio_below_to_plus_ci_high")
    if low is not None and high is not None:
        out.update(shift_keys(v, low, high))
    out.update(weather_shares(snaps))
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "smsr_variants.md").write_text(table_markdown(out), encoding="utf-8")
    return out


def table_markdown(metrics: dict) -> str:
    """The two variants side by side, for the README."""
    lines = ["| Miara | FAO-56 | Doroszewski–Górski |", "|---|---|---|"]
    for name in ("csi", "pod", "far", "peirce", "accuracy", "balanced_accuracy", "recall", "precision"):
        a, b = metrics.get(f"smsr.{name}_fao56"), metrics.get(f"smsr.{name}_dg")
        lines.append(f"| {name} | {a if a is not None else '–'} | {b if b is not None else '–'} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=1, sort_keys=True))
