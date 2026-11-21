"""Run the golden-path scenes once, headless, without video: does the demo work?

`make demo` (part of gate-fast) starts the app on $HN_PORT (or a free port),
runs demo/scenes.py in the system Chrome with pauses capped at 150 ms and prints
one line per scene. Exit 1 if any scene fails, the page throws, or the console
logs an error: the demo is a test. The recorded video runs separately, after the
merge. ui_audit.py reuses the helpers below.
"""

from __future__ import annotations

import importlib.util
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAUSE_CAP_MS = 150


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def up(url: str, timeout_s: float) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return r.status < 500
        except OSError:
            time.sleep(0.5)
    return False


def start_server(port: int) -> subprocess.Popen:
    return subprocess.Popen(["uv", "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True)


def stop_server(server: subprocess.Popen) -> None:
    try:
        os.killpg(server.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def load_scenes() -> list:
    spec = importlib.util.spec_from_file_location("scenes", ROOT / "demo" / "scenes.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return list(getattr(mod, "SCENES", []))


def launch(pw):
    try:
        return pw.chromium.launch(channel="chrome", headless=True)
    except Exception:  # noqa: BLE001 - fall back to a bundled chromium
        return pw.chromium.launch(headless=True)


def fast_pauses(page) -> None:
    """Scenes pause 1-2 s for the video viewer; a gate does not need that."""
    orig = page.wait_for_timeout
    page.wait_for_timeout = lambda ms: orig(min(ms, PAUSE_CAP_MS))


def main() -> int:
    port = int(os.environ.get("HN_PORT") or free_port())
    server = start_server(port)
    base = f"http://127.0.0.1:{port}"
    failed = 0
    try:
        if not up(base + "/health", 60):
            print(f"ERROR demo: server did not start on {base}")
            return 1
        scenes = load_scenes()
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = launch(pw)
            page = browser.new_page(viewport={"width": 1280, "height": 800}, locale="pl-PL")
            fast_pauses(page)
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"[:300]))
            page.on("console", lambda m: errors.append(f"console.error: {m.text}"[:300]) if m.type == "error" else None)
            for title, fn in scenes:
                t = time.time()
                try:
                    fn(page, base)
                    print(f"OK   {title} ({time.time() - t:.1f} s)")
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    print(f"ERROR scene '{title}': {type(e).__name__}: {str(e)[:300]}")
            browser.close()
        if errors:
            failed += 1
            print("ERROR browser errors during the demo:\n  " + "\n  ".join(errors[:10]))
    finally:
        stop_server(server)
    print("DEMO OK" if not failed else f"DEMO FAILED ({failed})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
