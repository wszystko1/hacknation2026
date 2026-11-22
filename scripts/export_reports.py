"""Save the print view of both demo parcels as PDF in docs/raporty/ (Playwright page.pdf).

    uv run python scripts/export_reports.py [output_dir]

Starts the app on a free port, opens /raport/druk for each demo parcel, waits until the photo has loaded
and writes one A4 file per parcel. The pages come from the frozen copies in demo/data, so no network is needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_demo import ROOT, free_port, launch, start_server, stop_server, up  # noqa: E402

OUT = ROOT / "docs" / "raporty"
PARCELS = {
    "dzialka-189-13-dobrcz-2023-07-20": {
        "dzialka": "040303_2.0002.189/13",
        "data": "2023-07-20",
        "uprawa": "zboza_jare",
    },
    "dzialka-144-gora-sw-malgorzaty-2026-11-21": {
        "dzialka": "100403_2.0011.144",
        "data": "2026-11-21",
        "uprawa": "rosliny_straczkowe",
    },
}


def export_one(params: dict, path: Path) -> Path:
    """Write the print view of one parcel as an A4 PDF at `path`."""
    from playwright.sync_api import sync_playwright

    port = free_port()
    server = start_server(port)
    try:
        base = f"http://127.0.0.1:{port}"
        if not up(base + "/health", 60):
            raise SystemExit("the app did not start")
        with sync_playwright() as pw:
            browser = launch(pw)
            page = browser.new_page(viewport={"width": 1100, "height": 1400})
            _save(page, base, params, path)
            browser.close()
    finally:
        stop_server(server)
    return path


def _save(page, base: str, params: dict, path: Path) -> None:
    page.goto(f"{base}/raport/druk?{urlencode(params)}", wait_until="networkidle", timeout=60000)
    page.wait_for_selector("#tabela-zrodel", state="attached")
    page.evaluate(
        "Promise.all([...document.images].map(i => i.complete || new Promise(r => { i.onload = i.onerror = r; })))"
    )
    page.pdf(path=str(path), format="A4", print_background=True, prefer_css_page_size=True)


def export(out_dir: Path = OUT) -> list[Path]:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    port = free_port()
    server = start_server(port)
    written: list[Path] = []
    try:
        base = f"http://127.0.0.1:{port}"
        if not up(base + "/health", 60):
            raise SystemExit("the app did not start")
        with sync_playwright() as pw:
            browser = launch(pw)
            page = browser.new_page(viewport={"width": 1100, "height": 1400})
            for name, params in PARCELS.items():
                path = out_dir / f"{name}.pdf"
                _save(page, base, params, path)
                written.append(path)
            browser.close()
    finally:
        stop_server(server)
    return written


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    for p in export(target):
        print(p)
