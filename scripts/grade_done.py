"""Grade DONE.json from evidence, not from opinions.

DONE.json:
{
  "task": "...",
  "criteria": [
    {"id": "K1", "name": "Zgodność z dane.gov.pl", "weight": 35, "required": true,
     "evidence": "co jury ma zobaczyć",
     "checks": [
       {"kind": "test",   "target": "tests/test_dcat.py"},
       {"kind": "scene",  "target": "Eksport do DCAT"},
       {"kind": "file",   "target": "docs/DCAT.md"},
       {"kind": "metric", "target": "f1", "min": 0.8}
     ]}
  ]
}

Writes artifacts/grade.json and artifacts/grade.md (the README's
"kryterium -> dowód" table). A criterion is green when all its checks pass,
amber when some do, red when none or it has no checks. Exit 0 always: this is
a measurement; the planner decides what to do with red rows.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def metric_value(metrics: dict, dotted: str):
    cur = metrics
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur if isinstance(cur, (int, float)) else None


def run_check(check: dict, metrics: dict, demo: dict) -> tuple[bool, str]:
    kind, target = check.get("kind"), str(check.get("target", ""))
    if kind == "file":
        ok = (ROOT / target).exists()
        return ok, target if ok else f"brak {target}"
    if kind == "test":
        try:
            r = subprocess.run(["uv", "run", "pytest", "-q", target], cwd=ROOT, capture_output=True,
                               text=True, timeout=240)
        except subprocess.TimeoutExpired:
            return False, f"{target}: timeout"
        return r.returncode == 0, f"{target}: " + (r.stdout.strip().splitlines() or ["?"])[-1]
    if kind == "metric":
        v = metric_value(metrics, target)
        lo = check.get("min")
        if v is None:
            return False, f"brak metryki {target}"
        ok = lo is None or v >= lo
        return ok, f"{target}={v}" + (f" (próg {lo})" if lo is not None else "")
    if kind == "scene":
        scenes = {s.get("title"): s for s in demo.get("scenes", [])}
        s = scenes.get(target)
        if not s:
            return False, f"scena '{target}' nie istnieje w ostatnim nagraniu"
        return bool(s.get("ok")), f"scena '{target}': {'ok' if s.get('ok') else s.get('error', 'błąd')}"
    return False, f"nieznany rodzaj {kind}"


def main() -> int:
    done = load(ROOT / "DONE.json", {"criteria": []})
    metrics = load(ROOT / "metrics.json", {})
    demo = load(ROOT / "artifacts" / "demo_result.json", {})
    rows = []
    for c in done.get("criteria", []):
        results = [run_check(ch, metrics, demo) for ch in c.get("checks", [])]
        passed = sum(1 for ok, _ in results if ok)
        status = "red" if not results or passed == 0 else ("green" if passed == len(results) else "amber")
        rows.append({"id": c.get("id"), "name": c.get("name"), "weight": c.get("weight", 0),
                     "required": c.get("required", False), "status": status,
                     "evidence": c.get("evidence", ""), "checks": [d for _, d in results]})
    total = sum(r["weight"] or 0 for r in rows) or 1
    score = sum((r["weight"] or 0) * {"green": 1, "amber": 0.5, "red": 0}[r["status"]] for r in rows) / total
    out = {"score_evidence": round(score, 3), "criteria": rows}
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts" / "grade.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    icon = {"green": "✅", "amber": "🟡", "red": "❌"}
    md = ["| Kryterium (waga) | Stan | Dowód |", "|---|---|---|"]
    for r in rows:
        md.append(f"| {r['name']} ({r['weight']}%) | {icon[r['status']]} | {'; '.join(r['checks']) or r['evidence']} |")
    (ROOT / "artifacts" / "grade.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nPokrycie kryteriów dowodami (ważone): {score:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
