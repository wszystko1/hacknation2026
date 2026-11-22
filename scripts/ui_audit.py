"""gate-full: the jury's view at three screen sizes, after every scene of the golden path.

For 1366x768 (a typical office laptop), 1920x1080 and 390x844 (phone) it runs
demo/scenes.py and after each scene checks:
- no horizontal scrolling;
- interactive elements do not overlap; on the phone, buttons are at least 44 px;
- text is at least 12 px (owner decision 22.11.2026: smaller type, 13 px body, 12 px for helper text); key text is not cut off;
- no lorem / TODO / FIXME / undefined / NaN on screen; no English labels;
- zero console errors, zero failed requests;
- axe-core (WCAG 2.1 A/AA): zero serious or critical violations.
Writes artifacts/ui_audit.json, one screenshot per scene and viewport, and a
contact sheet (artifacts/ui/sheet.png) for the panel. Prints `ERROR ...` lines;
exit 1 on any error.
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_demo import ROOT, fast_pauses, free_port, launch, load_scenes, start_server, stop_server, up  # noqa: E402

VIEWPORTS = [("laptop", 1366, 768), ("desktop", 1920, 1080), ("phone", 390, 844)]
BANNED = re.compile(r"\b(lorem|ipsum|TODO|FIXME|undefined|NaN)\b")
ENGLISH = {
    "submit",
    "search",
    "upload",
    "download",
    "cancel",
    "save",
    "next",
    "back",
    "loading",
    "loading...",
    "error",
    "settings",
    "home",
    "login",
    "log in",
    "sign in",
    "sign up",
    "dashboard",
    "delete",
    "edit",
    "close",
    "send",
    "results",
    "details",
    "filter",
    "export",
    "browse",
    "show",
    "hide",
    "show more",
    "welcome",
    "help",
    "overview",
    "reports",
    "summary",
    "add",
    "remove",
    "update",
    "create",
    "new",
    "view",
    "select",
    "choose",
    "run",
    "reset",
    "clear",
    "apply",
    "previous",
    "continue",
    "confirm",
    "upload file",
}
AXE = ROOT / "scripts" / "vendor" / "axe.min.js"

PROBE = """(phone) => {
  // Screen-reader-only text (.sr-only: 1x1 px, overflow hidden) is accessibility, not a cut label (smoke 18.11).
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const label = el => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 40);
  const out = {overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
               small: [], tap: [], overlap: [], truncated: [], offscreen: [], labels: []};
  const textEls = [...document.querySelectorAll('body *')].filter(el => vis(el) &&
    [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim().length > 1));
  for (const el of textEls) {
    const s = getComputedStyle(el); const fs = parseFloat(s.fontSize);
    if (fs < 12 && !el.closest('sup,sub,code,pre')) out.small.push(`${el.tagName.toLowerCase()} ${fs}px "${label(el)}"`);
    if ((s.overflowX === 'hidden' || s.overflow === 'hidden' || s.textOverflow === 'ellipsis') &&
        el.scrollWidth > el.clientWidth + 1) out.truncated.push(`${el.tagName.toLowerCase()} "${label(el)}"`);
    const r = el.getBoundingClientRect();   // smoke 18.11: a table in an overflow wrapper hid a column on the phone
    if (r.right > innerWidth + 2 || r.left < -2) out.offscreen.push(`${el.tagName.toLowerCase()} "${label(el)}" (${Math.round(r.left)}..${Math.round(r.right)} px)`);
  }
  const inter = [...document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,[role=button]')].filter(vis);
  for (const el of inter) {
    const r = el.getBoundingClientRect();
    const isButton = el.tagName === 'BUTTON' || el.tagName === 'SELECT' || el.getAttribute('role') === 'button' ||
      (el.tagName === 'INPUT' && ['submit', 'button', 'checkbox', 'radio'].includes(el.type));
    if (phone && isButton && (r.height < 44 || r.width < 44)) out.tap.push(`${el.tagName.toLowerCase()} ${Math.round(r.width)}x${Math.round(r.height)} "${label(el)}"`);
  }
  for (let i = 0; i < inter.length; i++) for (let j = i + 1; j < inter.length; j++) {
    const a = inter[i], b = inter[j];
    if (a.contains(b) || b.contains(a)) continue;
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const w = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
    const h = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
    if (w > 2 && h > 2) out.overlap.push(`"${label(a)}" x "${label(b)}"`);
  }
  for (const el of [...document.querySelectorAll('button,a,label,th,h1,h2,h3,legend,[placeholder],[role=button]')].filter(vis))
    out.labels.push((el.getAttribute('placeholder') || label(el)).toLowerCase());
  out.text = document.body.innerText;
  return out;
}"""

AXE_RUN = """async () => (await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}}))
  .violations.filter(v => ['serious', 'critical'].includes(v.impact))
  .map(v => ({id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length,
              target: v.nodes[0] ? v.nodes[0].target.join(' ') : ''}))"""


def audit_state(page, phone: bool) -> dict:
    p = page.evaluate(PROBE, phone)
    problems: dict[str, list] = {}
    if p["overflow"]:
        problems["poziome przewijanie"] = ["scrollWidth > clientWidth"]
    for key, name in (
        ("small", "tekst < 12 px"),
        ("tap", "cel kliknięcia < 44 px"),
        ("overlap", "nachodzące elementy"),
        ("truncated", "ucięty tekst"),
        ("offscreen", "tekst poza ekranem (np. tabela szersza niż ekran)"),
    ):
        if p[key]:
            problems[name] = p[key][:5]
    banned = sorted(set(BANNED.findall(p["text"])))
    if banned:
        problems["zakazany tekst"] = banned
    english = sorted({lab for lab in p["labels"] if lab.strip(" .:…") in ENGLISH})
    if english:
        problems["angielskie etykiety"] = english[:8]
    try:
        page.add_script_tag(path=str(AXE))
        axe = page.evaluate(AXE_RUN)
    except Exception as e:  # noqa: BLE001 - a page that blocks scripts still gets the other checks
        axe = [{"id": "axe-not-run", "impact": "serious", "help": str(e)[:200], "nodes": 0, "target": ""}]
    if axe:
        problems["axe (WCAG)"] = [
            f"{v['id']} [{v['impact']}] {v['help']} ({v['nodes']}x, np. {v['target']})" for v in axe
        ]
    return problems


def contact_sheet(browser, shots: list[tuple[str, bytes]], out: Path) -> None:
    cells = "".join(
        f'<figure><img src="data:image/png;base64,{base64.b64encode(b).decode()}"><figcaption>{t}</figcaption></figure>'
        for t, b in shots
    )
    html = (
        "<html><body style='margin:0;background:#eee;font:14px sans-serif'><div style='display:grid;"
        "grid-template-columns:repeat(3,1fr);gap:8px;padding:8px'>" + cells + "</div><style>img{width:100%;"
        "border:1px solid #999}figure{margin:0}</style></body></html>"
    )
    page = browser.new_page(viewport={"width": 1800, "height": 1000})
    page.set_content(html)
    page.screenshot(path=str(out), full_page=True)
    page.close()


def audit_viewport(
    browser, scenes, vp: str, w: int, h: int, out_dir: Path, report: dict, shots: list
) -> None:
    """One viewport on a fresh server: scenes may change server state, and the second pass of a
    publication scene on the same server failed (smoke 18.11)."""
    port = free_port()
    server = start_server(port)
    base = f"http://127.0.0.1:{port}"
    try:
        if not up(base + "/health", 60):
            report["errors"].append(f"ERROR [{vp}] server did not start on {base}")
            return
        phone = vp == "phone"
        ctx = browser.new_context(
            viewport={"width": w, "height": h}, locale="pl-PL", is_mobile=phone, has_touch=phone
        )
        page = ctx.new_page()
        fast_pauses(page)
        browser_errors: list[str] = []
        page.on("pageerror", lambda e: browser_errors.append(f"pageerror: {e}"[:200]))
        page.on(
            "console",
            lambda m: browser_errors.append(f"console.error: {m.text}"[:200]) if m.type == "error" else None,
        )
        page.on("requestfailed", lambda r: browser_errors.append(f"request failed: {r.url}"[:200]))
        page.on(
            "response",
            lambda r: (
                browser_errors.append(f"HTTP {r.status}: {r.url}"[:200])
                if r.status >= 400 and "favicon" not in r.url
                else None
            ),
        )
        rows = []
        for i, (title, fn) in enumerate(scenes, 1):
            row: dict = {"scene": title}
            try:
                fn(page, base)
                row["problems"] = audit_state(page, phone)
            except Exception as e:  # noqa: BLE001
                row["problems"] = {"scena nie przeszła": [f"{type(e).__name__}: {str(e)[:200]}"]}
            try:
                png = page.screenshot(path=str(out_dir / f"{vp}-{i:02d}.png"))
                shots.append((f"{vp} {w}x{h}: {title}", png))
            except Exception:  # noqa: BLE001
                pass
            for name, items in row["problems"].items():
                report["errors"].append(
                    f"ERROR [{vp} {w}x{h}] '{title}': {name}: {'; '.join(map(str, items))}"
                )
            rows.append(row)
        if browser_errors:
            report["errors"].append(
                f"ERROR [{vp} {w}x{h}] błędy przeglądarki: {'; '.join(browser_errors[:5])}"
            )
        report["viewports"][vp] = rows
        ctx.close()
    finally:
        stop_server(server)


def main() -> int:
    out_dir = ROOT / "artifacts" / "ui"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {"viewports": {}, "errors": []}
    shots: list[tuple[str, bytes]] = []
    scenes = load_scenes()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = launch(pw)
        for vp, w, h in VIEWPORTS:
            audit_viewport(browser, scenes, vp, w, h, out_dir, report, shots)
        try:
            contact_sheet(browser, shots, out_dir / "sheet.png")
            report["sheet"] = "artifacts/ui/sheet.png"
        except Exception as e:  # noqa: BLE001
            report["sheet_error"] = str(e)[:200]
        browser.close()
    (ROOT / "artifacts" / "ui_audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if report["errors"]:
        print("\n".join(report["errors"]))
        print(
            f"UI AUDIT FAILED ({len(report['errors'])}); details: artifacts/ui_audit.json, sheet: artifacts/ui/sheet.png"
        )
        return 1
    print("UI AUDIT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
