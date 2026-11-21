"""IMGW-PIB station archive: daily precipitation (rain gauges) and ET0 inputs (synoptic stations).

The archive is a tree of small zip files. `sync()` downloads them once into data/raw/imgw and builds
one index file (stations x days matrices), so a lookup for any point takes milliseconds.
"""

from __future__ import annotations

import calendar
import csv
import io
import json
import math
import re
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from . import config, http
from .et0 import et0_penman_monteith, radiation_from_sunshine

BASE_URL = "https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/dobowe/"
DEFAULT_START_YEAR = 2006
WIND_10M_TO_2M = 4.87 / math.log(67.8 * 10 - 5.42)  # FAO-56 eq. 47
_lock = threading.Lock()
_loaded: dict = {}


def imgw_dir() -> Path:
    return config.cache_dir().parent / "imgw"


def index_path() -> Path:
    return imgw_dir() / "index.npz"


def station_table() -> dict[str, tuple[str, float, float]]:
    """code -> (name, lon, lat) from the bundled coordinate table."""
    path = Path(__file__).parent / "data" / "imgw_stations.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return {r["code"]: (r["name"], float(r["lon"]), float(r["lat"])) for r in csv.DictReader(handle)}


def _download_year(kind: str, year: int) -> tuple[int, int]:
    """Download the zips of one year that are not on disk yet. Returns (new, total)."""
    folder = imgw_dir() / kind / str(year)
    url = f"{BASE_URL}{kind}/{year}/"
    resp = http.get(url, timeout=20.0, retries=2)
    if resp.status_code != 200:
        return 0, 0
    names = sorted(set(re.findall(r'href="([^"/]+\.zip)"', resp.text)))
    new = 0
    for name in names:
        target = folder / name
        if target.is_file() and target.stat().st_size > 0:
            continue
        got = http.get(url + name, timeout=30.0, retries=2)
        if got.status_code == 200 and got.content[:2] == b"PK":
            folder.mkdir(parents=True, exist_ok=True)
            target.write_bytes(got.content)
            new += 1
    return new, len(names)


def _number(value: str, status: str) -> float:
    """Value with its status column: "8" = no measurement, "9" = phenomenon absent (zero)."""
    status = status.strip()
    if status == "8":
        return math.nan
    if status == "9":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return math.nan


def _rows(path: Path, prefix: str):
    """CSV rows of the member whose name starts with `prefix` (files are cp1250, no header)."""
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.namelist():
                base = member.rsplit("/", 1)[-1].lower()
                if base.startswith(prefix) and not (prefix == "s_d_" and base.startswith("s_d_t_")):
                    text = archive.read(member).decode("cp1250", errors="replace")
                    yield from csv.reader(io.StringIO(text))
    except (zipfile.BadZipFile, OSError):
        return


def build_index(start_year: int = DEFAULT_START_YEAR, end_year: int | None = None) -> dict:
    """Parse every downloaded zip into stations x days matrices and write index.npz."""
    end_year = end_year or date.today().year
    day0 = date(start_year, 1, 1)
    n_days = (date(end_year, 12, 31) - day0).days + 1
    month_offset = {
        (y, m): (date(y, m, 1) - day0).days for y in range(start_year, end_year + 1) for m in range(1, 13)
    }
    stations = station_table()
    series: dict[str, dict[str, np.ndarray]] = {}

    def column(code: str, name: str) -> np.ndarray:
        per_station = series.setdefault(code, {})
        if name not in per_station:
            per_station[name] = np.full(n_days, np.nan, dtype="float32")
        return per_station[name]

    def day_index(row: list[str]) -> int | None:
        try:
            offset = month_offset.get((int(row[2]), int(row[3])))
            return None if offset is None else offset + int(row[4]) - 1
        except (ValueError, IndexError):
            return None

    for path in sorted((imgw_dir() / "opad").glob("*/*.zip")):
        # Gauge files before 2025 list only the days with precipitation. For a station that appears in a
        # monthly file, a day without a row is therefore a dry day; status "8" stays "no measurement".
        seen: dict[str, set[int]] = {}
        months: set[tuple[int, int]] = set()
        for row in _rows(path, "o_d_"):
            i = day_index(row)
            if i is not None and len(row) > 6:
                code = row[0].strip()
                column(code, "gauge")[i] = _number(row[5], row[6])
                seen.setdefault(code, set()).add(i)
                months.add((int(row[2]), int(row[3])))
        for year, month in months:
            first = month_offset[(year, month)]
            last = first + calendar.monthrange(year, month)[1]
            for code, days in seen.items():
                values = column(code, "gauge")
                for i in range(first, last):
                    if i not in days:
                        values[i] = 0.0
    for path in sorted((imgw_dir() / "synop").glob("*/*.zip")):
        for row in _rows(path, "s_d_"):
            i = day_index(row)
            if i is None or len(row) < 22:
                continue
            code = row[0].strip()
            column(code, "tmax")[i] = _number(row[5], row[6])
            column(code, "tmin")[i] = _number(row[7], row[8])
            column(code, "synop_precip")[i] = _number(row[13], row[14])
            column(code, "sun")[i] = _number(row[20], row[21])
        for row in _rows(path, "s_d_t_"):
            i = day_index(row)
            if i is None or len(row) < 17:
                continue
            code = row[0].strip()
            column(code, "wind")[i] = _number(row[7], row[8])
            column(code, "rh")[i] = _number(row[13], row[14])
            column(code, "pressure")[i] = _number(row[15], row[16])

    doy = np.array([(day0 + timedelta(days=i)).timetuple().tm_yday for i in range(n_days)], dtype="float64")
    p_codes, p_rows, e_codes, e_rows = [], [], [], []
    without_coords = 0
    for code, cols in sorted(series.items()):
        if code not in stations:
            without_coords += 1
            continue
        lat = stations[code][2]
        precip = cols.get("gauge")
        if precip is None:
            precip = cols.get("synop_precip")
        elif "synop_precip" in cols:
            precip = np.where(np.isnan(precip), cols["synop_precip"], precip)
        if precip is not None and np.isfinite(precip).any():
            p_codes.append(code)
            p_rows.append(precip)
        if all(k in cols for k in ("tmax", "tmin", "sun", "wind", "rh")):
            pressure = cols.get("pressure")
            mean_hpa = (
                float(np.nanmean(pressure))
                if pressure is not None and np.isfinite(pressure).any()
                else 1000.0
            )
            elevation = 44330.0 * (1.0 - (mean_hpa / 1013.25) ** 0.1903)
            f64 = {k: cols[k].astype("float64") for k in ("tmax", "tmin", "sun", "wind", "rh")}
            with np.errstate(invalid="ignore"):
                rs = radiation_from_sunshine(f64["sun"], doy, lat)
                et0 = et0_penman_monteith(
                    f64["tmax"], f64["tmin"], f64["rh"], f64["wind"] * WIND_10M_TO_2M, rs, doy, lat, elevation
                )
            if np.isfinite(et0).any():
                e_codes.append(code)
                e_rows.append(et0.astype("float32"))
    if not p_rows:
        raise RuntimeError(f"no IMGW files found in {imgw_dir()}; run the imgw-sync command first")
    meta = {
        "day0": day0.isoformat(), "n_days": n_days, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "precip": [[c, stations[c][0], stations[c][1], stations[c][2]] for c in p_codes],
        "et0": [[c, stations[c][0], stations[c][1], stations[c][2]] for c in e_codes],
        "stations_without_coordinates": without_coords,
    }  # fmt: skip
    imgw_dir().mkdir(parents=True, exist_ok=True)
    tmp = index_path().with_suffix(".tmp.npz")
    np.savez(
        tmp, precip=np.vstack(p_rows), et0=np.vstack(e_rows) if e_rows else np.zeros((0, n_days), "float32")
    )
    tmp.replace(index_path())
    index_path().with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    with _lock:
        _loaded.clear()
    return meta


def sync(start_year: int = DEFAULT_START_YEAR, end_year: int | None = None, workers: int = 6) -> dict:
    """Download missing archive files for the years and rebuild the index. Safe to re-run."""
    end_year = end_year or date.today().year
    jobs = [(kind, year) for kind in ("opad", "synop") for year in range(start_year, end_year + 1)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        counts = list(pool.map(lambda job: _download_year(*job), jobs))
    meta = build_index(start_year, end_year)
    meta["downloaded"] = sum(c[0] for c in counts)
    meta["files"] = sum(c[1] for c in counts)
    return meta


def load_index() -> dict | None:
    """The index, loaded once per process (reloaded when the file changes). None when it was never built."""
    path = index_path()
    if not path.is_file():
        return None
    stamp = path.stat().st_mtime
    with _lock:
        if _loaded.get("stamp") != stamp:
            meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            arrays = np.load(path)
            _loaded.clear()
            _loaded.update(
                stamp=stamp, meta=meta, day0=date.fromisoformat(meta["day0"]),
                precip=arrays["precip"], et0=arrays["et0"],
            )  # fmt: skip
        return _loaded


def index_stamp() -> str:
    index = load_index()
    return index["meta"]["built_at"] if index else ""


def _distance_km(lat1: float, lon1: float, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    p1, p2 = math.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def lookup(
    kind: str, lat: float, lon: float, start: date, end: date, *, max_km: float, max_stations: int = 3
) -> dict | None:
    """Daily values for the point: each day from the nearest station that has it.

    kind: "precip" (rain gauges and synoptic stations) or "et0" (synoptic stations only).
    Returns {"values": [float | None], "stations": [{"name", "code", "km", "days"}]} or None when the
    index is missing or no station lies within max_km.
    """
    index = load_index()
    if index is None:
        return None
    listed = index["meta"][kind]
    if not listed:
        return None
    lats, lons = np.array([s[3] for s in listed]), np.array([s[2] for s in listed])
    km = _distance_km(lat, lon, lats, lons)
    order = [int(i) for i in np.argsort(km)[:max_stations] if km[i] <= max_km]
    if not order:
        return None
    n = (end - start).days + 1
    lo = (start - index["day0"]).days
    out = np.full(n, np.nan, dtype="float64")
    matrix = index[kind]
    src_lo, src_hi = max(lo, 0), min(lo + n, matrix.shape[1])
    stations = []
    if src_hi > src_lo:
        view = slice(src_lo - lo, src_hi - lo)
        for i in order:
            row = matrix[i, src_lo:src_hi].astype("float64")
            take = np.isnan(out[view]) & np.isfinite(row)
            out[view] = np.where(take, row, out[view])
            if take.any():
                stations.append(
                    {
                        "name": listed[i][1],
                        "code": listed[i][0],
                        "km": round(float(km[i]), 1),
                        "days": int(take.sum()),
                    }
                )
    return {"values": [None if np.isnan(v) else round(float(v), 2) for v in out], "stations": stations}
