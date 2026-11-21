"""Where a commune page of SMSR comes from: frozen copy of the demo communes, disk cache, the downloaded
archive, or the live service (and then it goes to the disk cache).

A page of a finished year never changes, so it is kept for good; the page of the current year changes with
every day of the season and is reused for 12 hours.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.geodata import config, http
from app.geodata.errors import CacheMiss, UpstreamError

ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT / "demo" / "data" / "smsr"
CACHE_DIR = ROOT / "data" / "raw" / "smsr_cache"
ARCHIVE_DIR = ROOT / "data" / "raw" / "smsr"
URL = "https://susza.iung.pulawy.pl/wykazy/{year},{teryt}/"
CURRENT_YEAR_TTL_S = 12 * 3600
LIVE_DEADLINE_S = 6.0


class PageUnavailable(Exception):
    """No page for this commune and year; `reason` is the end of the sentence "Brak: …, bo <reason>"."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class Page:
    html: str
    origin: str  # "demo" | "cache" | "archive" | "live"
    retrieved_at: str  # ISO time of the original download
    elapsed_s: float  # the original download for stored pages, this request for live ones


def page_url(year: int, teryt: str) -> str:
    return URL.format(year=year, teryt=teryt)


def _name(year: int, teryt: str) -> str:
    return f"{year}_{teryt}"


def _read(folder: Path, year: int, teryt: str, origin: str, now: float, current_year: int) -> Page | None:
    path = folder / f"{_name(year, teryt)}.html"
    try:
        html = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    retrieved = str(meta.get("retrieved_at") or datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat())
    if origin != "demo" and year >= current_year:
        age = now - datetime.fromisoformat(retrieved).timestamp()
        if age > CURRENT_YEAR_TTL_S:
            return None
    return Page(html, origin, retrieved, float(meta.get("elapsed_s") or 0.0))


def _store(year: int, teryt: str, html: str, retrieved_at: str, elapsed_s: float) -> None:
    """Best effort: a cache that cannot be written (read-only disk) only costs the next request time."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / f"{_name(year, teryt)}.html"
        path.write_text(html, encoding="utf-8")
        path.with_suffix(".json").write_text(
            json.dumps({"retrieved_at": retrieved_at, "elapsed_s": round(elapsed_s, 2)}), encoding="utf-8"
        )
    except OSError:
        pass


def load_page(year: int, teryt: str, *, today: datetime | None = None) -> Page:
    """The page of the commune for the year. Raises PageUnavailable with the reason in Polish."""
    now = (today or datetime.now(UTC)).timestamp()
    current_year = (today or datetime.now(UTC)).year
    for folder, origin in ((DEMO_DIR, "demo"), (CACHE_DIR, "cache"), (ARCHIVE_DIR, "archive")):
        page = _read(folder, year, teryt, origin, now, current_year)
        if page:
            return page
    started = time.monotonic()
    try:
        resp = http.get(page_url(year, teryt), timeout=4.0, retries=1, deadline=started + LIVE_DEADLINE_S)
    except (UpstreamError, CacheMiss) as exc:
        raise PageUnavailable("wykaz IUNG nie odpowiedział") from exc
    elapsed = time.monotonic() - started
    if resp.status_code == 404:
        raise PageUnavailable(f"IUNG nie opublikował tabeli tej gminy za {year} r.")
    if resp.status_code != 200 or config.is_offline():
        raise PageUnavailable("wykaz IUNG nie odpowiedział")
    retrieved = datetime.now(UTC).isoformat(timespec="seconds")
    _store(year, teryt, resp.text, retrieved, elapsed)
    return Page(resp.text, "live", retrieved, elapsed)
