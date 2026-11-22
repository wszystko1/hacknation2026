"""Text check: filler phrases in user-facing text.

Checks README.md, docs/*.md (except logs) and the HTML templates. The list is
short on purpose (few false alarms) and only grows: when a reviewer flags a
phrase, add it to EXTRA in scripts/slop_extra.txt. Table rows ("| ...") are
skipped, because criterion names such as "Innowacyjność (30%)" come from the
organiser. Exit 1 lists every hit with file and line.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEMS_PL = [
    r"w dzisiejszym (?:dynamicznym|szybko)",
    r"nie tylko\b.{0,60}\bale (?:także|również)",
    r"\bkompleksow\w*",
    r"\binnowacyjn\w*",
    r"\brewolucyj\w*",
    r"\bprzełomow\w*",
    r"\bbezproblemow\w*",
    r"\bpłynn(?:ie|a integracja)\b",
    r"\bzrewolucjoniz\w*",
    r"\bnajnowocześniejsz\w*",
    r"\bw erze (?:AI|sztucznej)",
    r"\bświat(?:a|ie)? technologii\b",
    r"\bodkryj\w*\b",
    r"\bmagi[aei]\b",
]
STEMS_EN = [
    r"\bseamless\w*",
    r"\bleverag\w*",
    r"\bdelv(?:e|es|ing)\b",
    r"here'?s why",
    r"\bcutting[- ]edge\b",
    r"\bgame[- ]chang\w*",
    r"\bstate[- ]of[- ]the[- ]art\b",
    r"\brevolutioni[sz]\w*",
    r"\bunlock\w*\b",
    r"\bempower\w*",
    r"\bin today'?s (?:fast|dynamic)",
]


def patterns() -> list[re.Pattern]:
    extra = ROOT / "scripts" / "slop_extra.txt"
    words = STEMS_PL + STEMS_EN
    if extra.exists():
        words += [
            w.strip()
            for w in extra.read_text(encoding="utf-8").splitlines()
            if w.strip() and not w.startswith("#")
        ]
    return [re.compile(w, re.I) for w in words]


def files() -> list[Path]:
    if len(sys.argv) > 1:  # one file given: check only that file
        return [Path(a).resolve() for a in sys.argv[1:] if Path(a).exists()]
    out = [ROOT / "README.md"]
    out += [p for p in (ROOT / "docs").glob("*.md")]
    out += list((ROOT / "app" / "templates").rglob("*.html")) if (ROOT / "app" / "templates").exists() else []
    return [p for p in out if p.exists()]


def main() -> int:
    pats = patterns()
    hits = []
    for path in files():
        in_code = False
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if line.strip().startswith("```"):
                in_code = not in_code
            if in_code or line.lstrip().startswith("|"):
                continue
            for p in pats:
                m = p.search(line)
                if m:
                    hits.append(f"{path.relative_to(ROOT)}:{n}: '{m.group(0)}' -> {line.strip()[:120]}")
    if hits:
        print("check_text: slop phrases (rewrite: the thing and its number first, no adjectives):")
        print("\n".join(hits))
        return 1
    print("check_text OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
