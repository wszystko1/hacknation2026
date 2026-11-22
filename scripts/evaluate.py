"""`make eval`: run the evaluations and write their numbers into metrics.json (the only writer of that file).

Each evaluation is a script scripts/eval_<name>.py with `run() -> dict[str, float | int]` returning flat keys
("smsr.csi": 0.41). Keys of an evaluation that is skipped (its data missing) keep their previous values.
Usage: python scripts/evaluate.py [name ...]   (default: all of EVALUATIONS)
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "metrics.json"
EVALUATIONS = [
    "smsr", "causes", "soil", "forecast", "robustness", "period_variants", "soil_sensitivity", "retention",
    "ponds", "wet_zones",
]  # fmt: skip


def load(name: str):
    path = ROOT / "scripts" / f"eval_{name}.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"eval_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses and pickling look the module up by name
    spec.loader.exec_module(mod)
    return mod


def nest(flat: dict) -> dict:
    out: dict = {}
    for key, value in flat.items():
        cur = out
        *parents, leaf = key.split(".")
        for p in parents:
            cur = cur.setdefault(p, {})
        cur[leaf] = value
    return out


def flatten(tree: dict, prefix: str = "") -> dict:
    flat = {}
    for k, v in tree.items():
        key = f"{prefix}.{k}" if prefix else k
        flat.update(flatten(v, key) if isinstance(v, dict) else {key: v})
    return flat


def save(current: dict) -> None:
    METRICS.write_text(
        json.dumps(nest(current), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(names: list[str]) -> int:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    current = flatten(json.loads(METRICS.read_text(encoding="utf-8")) if METRICS.is_file() else {})
    for name in names or EVALUATIONS:
        mod = load(name)
        if mod is None:
            print(f"eval {name}: no scripts/eval_{name}.py yet, skipped")
            continue
        started = time.monotonic()
        result = mod.run()
        if not result:
            print(f"eval {name}: skipped (no data), previous values kept")
            continue
        current.update(result)
        save(current)  # the next evaluation reads the keys of this one from the file
        print(f"eval {name}: {len(result)} values in {time.monotonic() - started:.1f} s")
    save(current)
    print(f"metrics.json: {len(current)} values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
