"""Benchmark: every parcel once with an empty cache (cold) and once again (warm)."""

from __future__ import annotations

import os
import platform
import statistics
import time
from datetime import datetime
from pathlib import Path

from . import config
from .cli import read_jobs, summary_line
from .orchestrator import ALL_SOURCES, fetch_all


def default_jobs_file() -> Path:
    return config.demo_dir() / "benchmark_parcels.txt"


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


def _table(title: str, runs: list) -> list[str]:
    lines = [
        f"### {title}",
        "",
        "| source | p50 ms | p95 ms | max ms | statuses |",
        "|---|---:|---:|---:|---|",
    ]
    for name in ALL_SOURCES:
        times = [getattr(r, name).elapsed_ms for r in runs]
        statuses: dict[str, int] = {}
        for r in runs:
            statuses[getattr(r, name).status] = statuses.get(getattr(r, name).status, 0) + 1
        text = ", ".join(f"{k}: {v}" for k, v in sorted(statuses.items()))
        lines.append(
            f"| {name} | {statistics.median(times):.0f} | {percentile(times, 0.95):.0f} | {max(times)} | {text} |"
        )
    totals = [r.total_ms for r in runs]
    core = sum(1 for r in runs if r.core_ok)
    lines.append(
        f"| **total** | {statistics.median(totals):.0f} | {percentile(totals, 0.95):.0f} | {max(totals)} | core ok: {core}/{len(runs)} |"
    )
    return [*lines, ""]


def provider_of(res) -> str:
    """Who actually served a source (for the benchmark table)."""
    if not res.usable:
        return res.status
    data = res.data
    if res.source == "weather":
        rain = ", ".join(f"{k} {v:.0%}" for k, v in data.precipitation_sources.items())
        et0 = ", ".join(f"{k} {v:.0%}" for k, v in data.et0_sources.items())
        return f"opad: {rain}; ET0: {et0}"
    if hasattr(data, "provider"):
        return data.provider
    host = res.source_url.split("/")[2] if "//" in res.source_url else res.source_url
    return f"{host} (brak danych)" if res.status == "fallback" else host


def providers_table(runs: list) -> list[str]:
    lines = [
        "### Dostawcy danych w przebiegu zimnym",
        "",
        "| source | dostawca: liczba działek |",
        "|---|---|",
    ]
    for name in ALL_SOURCES:
        counts: dict[str, int] = {}
        for r in runs:
            if name == "weather" and getattr(r, name).usable:
                d = getattr(r, name).data
                key = f"opad {d.precipitation_provider}, ET0 {d.et0_provider}"
            else:
                key = provider_of(getattr(r, name))
            counts[key] = counts.get(key, 0) + 1
        lines.append(f"| {name} | " + "; ".join(f"{k}: {v}" for k, v in sorted(counts.items())) + " |")
    lines += ["", "Pogoda w poszczególnych działkach (udział dni w zwróconym zakresie):", ""]
    lines += [f"- {r.parcel_id} ({r.date}): {provider_of(r.weather)}" for r in runs]
    return [*lines, ""]


def run_benchmark(jobs_file: Path | None, n: int, out: Path, budget_s: float) -> int:
    jobs = read_jobs(jobs_file or default_jobs_file(), datetime.now().date().isoformat())[:n]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bench_cache = config.cache_dir().parent / f"geodata_bench_{stamp}"
    previous = os.environ.get("GEODATA_CACHE_DIR")
    os.environ["GEODATA_CACHE_DIR"] = str(bench_cache)
    cold, warm = [], []
    try:
        for pid, day in jobs:
            cold.append(fetch_all(pid, day, budget_s=budget_s))
            print("cold", summary_line(cold[-1]))
            time.sleep(1.0)  # be polite to the public services; also lets late downloads reach the cache
        for pid, day in jobs:
            warm.append(fetch_all(pid, day, budget_s=budget_s))
            print("warm", summary_line(warm[-1]))
    finally:
        if previous is None:
            os.environ.pop("GEODATA_CACHE_DIR", None)
        else:
            os.environ["GEODATA_CACHE_DIR"] = previous
    lines = [
        "# Benchmark warstwy danych",
        "",
        f"Pomiar: {datetime.now().isoformat(timespec='seconds')}, {platform.system()} {platform.machine()}, "
        f"Python {platform.python_version()}, {len(jobs)} działek, budżet {budget_s:.0f} s na działkę.",
        "Zimny = pusty cache, wszystkie źródła z sieci. Ciepły = drugie wywołanie tej samej działki i daty.",
        "Czasy źródeł biegną równolegle, więc suma kolumn nie równa się czasowi całkowitemu.",
        "",
        *_table("Zimny cache", cold),
        *_table("Ciepły cache", warm),
        *providers_table(cold),
        "### Działki",
        "",
        "| działka | data | zimny ms | ciepły ms | uwagi (zimny) |",
        "|---|---|---:|---:|---|",
    ]
    for c, w in zip(cold, warm, strict=True):
        issues = "; ".join(f"{k}={v.status}" for k, v in c.sources().items() if v.status != "ok") or "-"
        lines.append(f"| {c.parcel_id} | {c.date} | {c.total_ms} | {w.total_ms} | {issues} |")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {out}; benchmark cache: {bench_cache}")
    return 0 if all(r.core_ok for r in cold) else 1
