"""Claims gate: numbers and test counts in README.md must match the evidence.

The most common red flag in 62 HackYeah 2026 reviews was a claim the code did
not back ("README claims 76 tests; 46 measured"). Two checks:

1. Metric-like numbers (percentages, decimals, numbers next to a metric word)
   must appear in metrics.json or docs/DANE.md, in any of their usual forms
   (0.91 = 91% = 91,0%).
2. "N testów / N tests" must not exceed the number of tests pytest collects.

Lines in code blocks are skipped. Exit 1 lists every unverified claim.

Strict when HN_CLAIMS_STRICT=1 or when README.md changed on this branch or in the working tree; otherwise
stale numbers after a new evaluation are a warning until the README is next edited.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METRIC_WORDS = re.compile(
    r"precyzj|czułoś|trafnoś|skuteczno|dokładno|accuracy|precision|recall|\bF1\b|f1|AUC|błęd|"
    r"fałszyw|false|latenc|opóźnien|czas odpowiedzi|przypadk|rekord|próbk|sample|ms\b|sekund|minut|"
    r"oszczędno|szybciej|razy\b|x\b",
    re.I,
)
NUMBER = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*(%|proc)?")
TEST_CLAIM = re.compile(r"(\d+)\s*(?:test(?:y|ów|s)?\b|przypadk\w* testow)", re.I)


def flatten(obj, out: set[str]) -> None:
    if isinstance(obj, dict):
        for v in obj.values():
            flatten(v, out)
    elif isinstance(obj, list):
        for v in obj:
            flatten(v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.update(forms(float(obj)))
    elif isinstance(obj, str):
        for m in NUMBER.finditer(obj):
            out.update(forms(float(m.group(1).replace(",", "."))))


def forms(x: float) -> set[str]:
    vals = {x}
    if 0 < abs(x) <= 1:
        vals.add(x * 100)
    if 1 < abs(x) <= 100:
        vals.add(x / 100)
    out = set()
    for v in vals:
        for nd in (0, 1, 2, 3):
            out.add(f"{round(v, nd):.{nd}f}")
    return out


def known_numbers() -> set[str]:
    out: set[str] = set()
    for name in ("metrics.json", "artifacts/grade.json"):
        p = ROOT / name
        if p.exists():
            try:
                flatten(json.loads(p.read_text(encoding="utf-8")), out)
            except json.JSONDecodeError:
                pass
    dane = ROOT / "docs" / "DANE.md"
    if dane.exists():
        flatten(dane.read_text(encoding="utf-8"), out)
    return out


def collected_tests() -> int | None:
    try:
        r = subprocess.run(
            ["uv", "run", "pytest", "--collect-only", "-q"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = r.stdout + r.stderr
    m = re.search(r"(\d+) tests? collected", text)
    if m:
        return int(m.group(1))
    per_file = re.findall(r"^\S+\.py: (\d+)$", text, flags=re.M)  # pytest -qq format
    if per_file:
        return sum(int(n) for n in per_file)
    return sum(1 for line in text.splitlines() if "::" in line) or None


def strict() -> bool:
    if os.environ.get("HN_CLAIMS_STRICT") == "1":
        return True

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)

    if git("status", "--porcelain", "--", "README.md").stdout.strip():
        return True  # edited right now
    base = git("merge-base", "HEAD", "main").stdout.strip()
    if base and git("diff", "--quiet", base, "HEAD", "--", "README.md").returncode == 1:
        return True  # this branch changed the README
    return False


def main() -> int:
    readme = ROOT / "README.md"
    if not readme.exists():
        print("check_claims OK (no README)")
        return 0
    known = known_numbers()
    problems = []
    test_count = None
    in_code = False
    for n, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        for m in TEST_CLAIM.finditer(line):
            if test_count is None:
                test_count = collected_tests() or 0
            if int(m.group(1)) > test_count:
                problems.append(f"README.md:{n}: claims {m.group(1)} tests, pytest collects {test_count}")
        metricish = METRIC_WORDS.search(line)
        for m in NUMBER.finditer(line):
            raw, pct = m.group(1), m.group(2)
            is_decimal = "." in raw or "," in raw
            if not (pct or is_decimal or metricish):
                continue
            value = float(raw.replace(",", "."))
            if value in (0, 1, 2, 3, 4, 5, 10, 24, 100) and not pct and not is_decimal:
                continue
            if TEST_CLAIM.search(line[m.start() : m.start() + 30]):
                continue
            if not forms(value) & known:
                problems.append(
                    f"README.md:{n}: number {raw}{pct or ''} not found in metrics.json / docs/DANE.md -> {line.strip()[:110]}"
                )
    if problems and not strict():
        print(
            f"check_claims WARN: {len(problems)} README number(s) not in metrics.json (README unchanged here; "
            "the README pass at the next checkpoint updates them)"
        )
        print("\n".join(problems[:5]))
        return 0
    if problems:
        print(
            "check_claims: unverified claims (write the number into metrics.json from a script, or drop it):"
        )
        print("\n".join(problems))
        return 1
    print("check_claims OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
