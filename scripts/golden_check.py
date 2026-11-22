#!/usr/bin/env python3
"""Golden locations against a running application: runs tests/golden with --base-url and writes a Markdown report.

Usage: python scripts/golden_check.py BASE_URL [--only ID] [--out FILE] [--offline]
The report goes to docs/notes/golden-wynik-<date>.md: a summary on top ("N of M; the list of failures"), then
the table location x category (PASS / FAIL / XFAIL with the reason), then the times. Exit code 1 on any FAIL.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ["verdict", "causes", "actions", "retention", "text", "perf", "negative"]
LABELS = {
    "verdict": "werdykt", "causes": "przyczyny", "actions": "działania", "retention": "retencja",
    "text": "tekst", "perf": "wydajność", "negative": "kontrole negatywne",
}


def run_pytest(base_url: str | None, only: str | None, junit: Path) -> int:
    cmd = [sys.executable, "-m", "pytest", "tests/golden", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}"]
    if base_url:
        cmd += ["--base-url", base_url]
    if only:
        cmd += ["--golden-only", only]
    return subprocess.call(cmd, cwd=ROOT)


def parse(junit: Path) -> list[dict]:
    rows = []
    for case in ET.parse(junit).getroot().iter("testcase"):
        name = case.get("name", "")
        if "@" not in name:
            continue
        loc, check = name[name.index("[") + 1 : -1].split("@", 1)
        status, detail = "PASS", ""
        for child in case:
            msg = (child.get("message") or child.text or "").strip().replace("\n", " ")
            if child.tag in ("failure", "error"):
                status, detail = "FAIL", msg
            elif child.tag == "skipped":
                if child.get("type") == "pytest.xfail":
                    status, detail = "XFAIL", msg.removeprefix("expected failure: ")
                else:
                    status, detail = "SKIP", msg
        rows.append({"loc": loc, "check": check, "cat": check.split(".")[0], "status": status,
                     "detail": detail, "time": float(case.get("time") or 0)})
    return rows


def cell(rows: list[dict]) -> str:
    states = {r["status"] for r in rows}
    if not states or states == {"SKIP"}:
        return "n/d"
    if "FAIL" in states:
        return "FAIL"
    if "XFAIL" in states:
        return "XFAIL"
    return "PASS"


def report(rows: list[dict], base_url: str | None, only: str | None) -> str:
    locs = list(OrderedDict.fromkeys(r["loc"] for r in rows if not (only and r["loc"] != only)))
    active = [r for r in rows if r["status"] != "SKIP"]
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("PASS", "FAIL", "XFAIL", "SKIP")}
    fails = [r for r in rows if r["status"] == "FAIL"]
    out = [f"# Wynik testów złotych lokalizacji, {date.today().isoformat()}", ""]
    out.append(f"Tryb: {'na żywo, ' + base_url if base_url else 'offline, dane zamrożone'}"
               + (f"; tylko {only}" if only else ""))
    out.append("")
    out.append(f"**{counts['PASS']} z {len(active)} kontroli spełnionych** (XFAIL: {counts['XFAIL']} znanych wad, "
               f"FAIL: {counts['FAIL']}, pominięte: {counts['SKIP']}).")
    out.append("")
    if fails:
        out.append("Niepowodzenia:")
        out += [f"- `{r['loc']}` / `{r['check']}`: {r['detail'][:300]}" for r in fails]
    else:
        out.append("Niepowodzeń (FAIL) brak.")
    out += ["", "## Lokalizacja × kategoria", "", "| lokalizacja | " + " | ".join(LABELS[c] for c in CATEGORIES) + " |",
            "|---|" + "---|" * len(CATEGORIES)]
    for loc in locs:
        out.append(f"| {loc} | " + " | ".join(cell([r for r in rows if r["loc"] == loc and r["cat"] == c])
                                              for c in CATEGORIES) + " |")
    out += ["", "## Znane wady (XFAIL) wg powodu", ""]
    reasons: dict[str, list[str]] = {}
    for r in rows:
        if r["status"] == "XFAIL":
            reasons.setdefault(f"{r['check']}: {r['detail']}", []).append(r["loc"])
    for reason, where in sorted(reasons.items()):
        out.append(f"- {reason} (lokalizacje: {len(where)})")
    out += ["", "## Czasy (s)", "", "| lokalizacja | raport zimny | raport ciepły | druk |", "|---|---|---|---|"]
    for loc in locs:
        t = {r["check"]: r["time"] for r in rows if r["loc"] == loc}
        out.append(f"| {loc} | {t.get('perf.cold', 0):.2f} | {t.get('perf.warm', 0):.2f} | {t.get('perf.print', 0):.2f} |")
    out.append("")
    out.append("Czas zimny dotyczy pierwszego zapytania w przebiegu (po rozgrzewce: ciepły); czas całej kontroli liczy się razem z pobraniem danych.")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url", nargs="?", help="address of the running application; omitted: offline")
    ap.add_argument("--only", help="id of one location (e.g. dobrcz)")
    ap.add_argument("--out", help="report file (default docs/notes/golden-wynik-<date>.md)")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        run_pytest(args.base_url, args.only, junit)
        if not junit.exists():
            print("pytest nie zapisał wyniku", file=sys.stderr)
            return 2
        rows = parse(junit)
    text = report(rows, args.base_url, args.only)
    out = Path(args.out) if args.out else ROOT / "docs" / "notes" / f"golden-wynik-{date.today().isoformat()}.md"
    out.write_text(text, encoding="utf-8")
    print(text.split("\n## ")[0])
    print(f"Raport: {out}")
    return 1 if any(r["status"] == "FAIL" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
