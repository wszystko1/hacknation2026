"""Command line: python -m app.geodata <fetch|prewarm|benchmark|export-samples> ..."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import config
from .orchestrator import ALL_SOURCES, fetch_all


def read_jobs(path: Path, default_day: str) -> list[tuple[str, str]]:
    """Lines "parcel_id[;date]" (also tab or comma before the date); "#" starts a comment."""
    jobs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for sep in (";", "\t", ","):
            if sep in line:
                pid, day = (part.strip() for part in line.split(sep, 1))
                break
        else:
            pid, day = line, default_day
        jobs.append((pid, day or default_day))
    return jobs


def summary_line(result) -> str:
    parts = [
        f"{n}={r.status}/{r.elapsed_ms}ms{'*' if r.from_cache else ''}" for n, r in result.sources().items()
    ]
    return f"{result.parcel_id} {result.date} total={result.total_ms}ms core_ok={result.core_ok} " + " ".join(
        parts
    )


def _cmd_fetch(args) -> int:
    result = fetch_all(args.parcel_id, args.date, budget_s=args.budget, offline=args.offline or None)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=1))
    else:
        print(summary_line(result))
        for name, res in result.sources().items():
            for note in [*res.notes, *([res.error] if res.error else [])]:
                print(f"  {name}: {note}")
    if args.ortho_out and result.ortho.usable:
        Path(args.ortho_out).write_bytes(result.ortho.data.image)
    return 0 if result.core_ok else 1


def _cmd_prewarm(args) -> int:
    from . import imgw

    if imgw.load_index() is None and not args.offline:
        print("IMGW station index missing: downloading the archive once (about a minute)")
        imgw.sync()
    jobs = read_jobs(Path(args.file), date.today().isoformat())
    failed = 0
    for pid, day in jobs:
        try:
            # A generous budget: the goal is a full cache, not a fast answer.
            result = fetch_all(pid, day, budget_s=args.budget, offline=args.offline or None)
        except ValueError as exc:
            print(f"{pid} {day} INVALID: {exc}")
            failed += 1
            continue
        print(summary_line(result))
        missing = [n for n, r in result.sources().items() if not r.usable]
        if missing:
            print(f"  not cached: {', '.join(missing)}")
        failed += 0 if result.core_ok else 1
    print(f"prewarm: {len(jobs) - failed}/{len(jobs)} with core data; cache: {config.cache_dir()}")
    return 0 if failed == 0 else 1


def _cmd_imgw_sync(args) -> int:
    from . import imgw

    meta = imgw.sync(args.start_year)
    print(
        f"IMGW: {meta['downloaded']} new of {meta['files']} files; index from {meta['day0']}: "
        f"{len(meta['precip'])} precipitation stations, {len(meta['et0'])} stations with ET0, "
        f"{meta['stations_without_coordinates']} stations skipped (no coordinates); {imgw.index_path()}"
    )
    return 0


def _cmd_benchmark(args) -> int:
    from .bench import run_benchmark

    return run_benchmark(Path(args.file) if args.file else None, args.n, Path(args.out), args.budget)


def _cmd_export(args) -> int:
    from .samples import save_sample

    for pid, day in read_jobs(Path(args.file), date.today().isoformat()):
        result = fetch_all(
            pid, day, budget_s=args.budget, ortho_max_px=args.ortho_px, offline=args.offline or None
        )
        print(summary_line(result))
        if result.core_ok:
            print(f"  saved {save_sample(result)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="python -m app.geodata", description="Parcel data download and cache"
    )
    parser.add_argument("--offline", action="store_true", help="serve only from the cache, report misses")
    parser.add_argument(
        "--cache-dir", help="cache directory (default data/raw/geodata_cache or GEODATA_CACHE_DIR)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="fetch one parcel and print the status of every source")
    p.add_argument("parcel_id")
    p.add_argument("date", nargs="?", default=date.today().isoformat())
    p.add_argument("--budget", type=float, default=25.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--ortho-out", help="write the orthophoto JPEG to this file")
    p.set_defaults(func=_cmd_fetch)

    p = sub.add_parser("prewarm", help="fill the cache for a file of 'parcel_id;date' lines")
    p.add_argument("file")
    p.add_argument("--budget", type=float, default=60.0)
    p.set_defaults(func=_cmd_prewarm)

    p = sub.add_parser("imgw-sync", help="download the IMGW daily archive once and build the station index")
    p.add_argument("--start-year", type=int, default=2006)
    p.set_defaults(func=_cmd_imgw_sync)

    p = sub.add_parser("benchmark", help="cold and warm timings, written to a Markdown file")
    p.add_argument("--file", help="'parcel_id;date' lines (default: the bundled list of farmland parcels)")
    p.add_argument("-n", type=int, default=10)
    p.add_argument("--budget", type=float, default=25.0)
    p.add_argument("--out", default=str(config.repo_root() / "docs" / "BENCHMARK.md"))
    p.set_defaults(func=_cmd_benchmark)

    p = sub.add_parser("export-samples", help="freeze results into demo/data/geodata")
    p.add_argument("file")
    p.add_argument("--budget", type=float, default=60.0)
    p.add_argument("--ortho-px", type=int, default=512)
    p.set_defaults(func=_cmd_export)

    args = parser.parse_args(argv)
    if args.cache_dir:
        os.environ["GEODATA_CACHE_DIR"] = args.cache_dir
    if args.offline:
        config.set_offline(True)
    return args.func(args)


__all__ = ["main", "read_jobs", "summary_line", "ALL_SOURCES"]
