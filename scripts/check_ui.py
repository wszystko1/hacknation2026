"""Static UI rules from docs/DESIGN.md, as a gate (part of gate-fast).

- Colours live only in the tokens (`:root` blocks of app/static/app.css). A hex,
  rgb() or hsl() literal anywhere else in CSS or templates is an error.
- No inline `style="..."` in templates: components take a role (class), not a value.
- No new UI dependency from a CDN (<script src="http..."> or <link href="http...">)
  unless docs/DESIGN.md lists its host under "Allowed UI dependencies".
Prints `ERROR file:line reason` lines; exit 1 on any error.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLOR = re.compile(r"(?<=[\s:,(])#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
INLINE_STYLE = re.compile(r"\sstyle\s*=\s*[\"']", re.I)
EXTERNAL = re.compile(r"<(?:script|link)\b[^>]*(?:src|href)\s*=\s*[\"'](https?:)?//([^/\"']+)", re.I)


def allowed_hosts() -> set[str]:
    design = ROOT / "docs" / "DESIGN.md"
    if not design.exists():
        return set()
    text = design.read_text(encoding="utf-8")
    m = re.search(r"Allowed UI dependencies.*?\n((?:\s*[-*].*\n?)*)", text, re.S)
    return set(re.findall(r"([a-z0-9.-]+\.[a-z]{2,})", m.group(1))) if m else set()


def strip_root_blocks(css: str) -> str:
    """Blank out `:root { ... }` blocks (the tokens), keeping line numbers."""
    out, i = [], 0
    for m in re.finditer(r":root[^{]*\{[^}]*\}", css):
        out.append(css[i:m.start()])
        out.append(re.sub(r"[^\n]", " ", m.group(0)))
        i = m.end()
    out.append(css[i:])
    return "".join(out)


def main() -> int:
    errors: list[str] = []
    hosts = allowed_hosts()
    static = ROOT / "app" / "static"
    for css in sorted(static.rglob("*.css")) if static.exists() else []:
        text = strip_root_blocks(css.read_text(encoding="utf-8", errors="ignore"))
        for n, line in enumerate(text.splitlines(), 1):
            if COLOR.search(line):
                errors.append(f"ERROR {css.relative_to(ROOT)}:{n} colour literal outside the tokens; "
                              f"use var(--token) or add a token in :root -> {line.strip()[:100]}")
    templates = ROOT / "app" / "templates"
    for html in sorted(templates.rglob("*.html")) if templates.exists() else []:
        for n, line in enumerate(html.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if INLINE_STYLE.search(line):
                errors.append(f"ERROR {html.relative_to(ROOT)}:{n} inline style; give the element a class "
                              f"in app.css -> {line.strip()[:100]}")
            for m in EXTERNAL.finditer(line):
                host = m.group(2).lower()
                if host not in hosts:
                    errors.append(f"ERROR {html.relative_to(ROOT)}:{n} UI dependency from {host}; vendor it into "
                                  "app/static/ or list its host under Allowed UI dependencies")
    if errors:
        print("\n".join(errors))
        print(f"check_ui: {len(errors)} error(s); rules in docs/DESIGN.md")
        return 1
    print("check_ui OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
