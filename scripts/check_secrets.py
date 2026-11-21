"""gate-full: no secrets in tracked files (API keys, private keys, tokens, passwords).

Scans `git ls-files` (or the working tree without git). Prints `ERROR file:line kind`;
exit 1 on any hit. A false positive gets `# not-a-secret` on the same line.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    "Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9]{32,}"),
    "AWS key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "password in code": re.compile(r"(?i)\b(password|passwd|secret|api_key|token)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"),
}
SKIP = re.compile(r"\.(png|jpe?g|gif|webp|pdf|zip|gz|parquet|xlsx?|lock|min\.js)$|^scripts/check_secrets\.py$")


def tracked() -> list[str]:
    r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.splitlines()
    return [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and ".venv" not in p.parts]


def main() -> int:
    hits = []
    for rel in tracked():
        if SKIP.search(rel):
            continue
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if "not-a-secret" in line:
                continue
            for kind, pat in PATTERNS.items():
                if pat.search(line):
                    hits.append(f"ERROR {rel}:{n} {kind}")
    if hits:
        print("\n".join(hits[:50]))
        print("check_secrets: remove the secret, rotate it, read it from the environment instead")
        return 1
    print("check_secrets OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
