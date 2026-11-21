"""The commune sample for the SMSR agreement measurement: demo/data/eval/gminy.csv.

    uv run python scripts/fetch_communes.py [--per-voivodeship 12] [--seed 2026]

1. The list of communes comes from the selectors of https://susza.iung.pulawy.pl/wykazy/ (16 voivodeships ->
   powiats -> communes); saved in data/raw/smsr/communes.json, so a rerun does not ask again.
2. Rural and urban-rural communes (TERYT type 2 and 3) are drawn at random inside each voivodeship with a fixed
   seed; urban communes are left out because they have almost no farmland.
3. Coordinates: the place named like the commune, from the Open-Meteo geocoding service (GeoNames), matched by
   voivodeship, powiat and commune. It is the seat, not the geometric centre; for weather it is within ~10 km.
   A commune without a match is replaced by the next one drawn.
4. 50 communes go to the development set and the rest to the test set (strata kept: every voivodeship has both).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://susza.iung.pulawy.pl/wykazy"
GEOCODER = "https://geocoding-api.open-meteo.com/v1/search"
LIST_PATH = ROOT / "data" / "raw" / "smsr" / "communes.json"
OUT_PATH = ROOT / "demo" / "data" / "eval" / "gminy.csv"
PAUSE_S = 0.5
DEV_TOTAL = 50
COLUMNS = ["teryt", "nazwa", "wojewodztwo", "lon", "lat", "zbior"]


def options(html: str, select_id: str) -> list[tuple[str, str]]:
    """(value, label) of the options of one <select> on a SMSR page, without the "-Wybierz-" entry."""
    block = re.search(rf'<select[^>]*id="{select_id}"[^>]*>(.*?)</select>', html, re.S)
    found = re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', block.group(1)) if block else []
    return [(value, label.strip()) for value, label in found if value not in {"", "-"}]


def get(client: httpx.Client, url: str, **params: str) -> httpx.Response:
    time.sleep(PAUSE_S)
    for attempt in range(3):
        try:
            resp = client.get(url, params=params or None, timeout=20)
            if resp.status_code == 200:
                return resp
        except httpx.HTTPError:
            pass
        time.sleep(2 * (attempt + 1))
    raise SystemExit(f"no answer from {url}")


def list_communes(client: httpx.Client, path: Path = LIST_PATH) -> list[dict[str, str]]:
    """All communes of the SMSR selectors: teryt, name, voivodeship, powiat."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    out: list[dict[str, str]] = []
    voivodeships = options(get(client, f"{BASE}/2024,04/").text, "sel-woj")
    for woj_code, woj_name in voivodeships:
        print("voivodeship", woj_name, file=sys.stderr)
        for pow_code, pow_name in options(get(client, f"{BASE}/2024,{woj_code}/").text, "sel-pow"):
            for teryt, name in options(get(client, f"{BASE}/2024,{pow_code}/").text, "sel-gmina"):
                out.append({"teryt": teryt, "nazwa": name, "wojewodztwo": woj_name, "powiat": pow_name})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"list not saved: {exc}", file=sys.stderr)
    return out


def geocode(client: httpx.Client, commune: dict[str, str]) -> tuple[float, float] | None:
    """Longitude and latitude of the place named like the commune inside its voivodeship; None without a match."""
    time.sleep(PAUSE_S)
    try:
        resp = client.get(
            GEOCODER,
            params={"name": commune["nazwa"], "country_code": "PL", "count": 30, "language": "pl"},
            timeout=20,
        )
        results = resp.json().get("results", []) if resp.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        return None
    woj = f"województwo {commune['wojewodztwo']}".casefold()
    powiat = f"powiat {commune['powiat']}".casefold()
    name = commune["nazwa"].casefold()
    in_woj = [r for r in results if (r.get("admin1") or "").casefold() == woj]
    pool = [r for r in in_woj if (r.get("admin3") or "").casefold() == name] or [
        r
        for r in in_woj
        if (r.get("admin2") or "").casefold() == powiat and (r.get("name") or "").casefold() == name
    ]
    if not pool:
        return None
    pool.sort(
        key=lambda r: ((r.get("admin2") or "").casefold() == powiat, r.get("population") or 0), reverse=True
    )
    return round(pool[0]["longitude"], 4), round(pool[0]["latitude"], 4)


def quotas(n_voivodeships: int, per: int, total: int) -> list[int]:
    """Sizes of the strata: `per` each, the remainder to the first ones, so that the sum is `total`."""
    sizes = [per] * n_voivodeships
    for i in range(total - per * n_voivodeships):
        sizes[i % n_voivodeships] += 1
    return sizes


def draw(communes: list[dict[str, str]], client: httpx.Client, total: int, seed: int) -> list[dict]:
    """Stratified sample: per voivodeship a seeded shuffle, the first communes with coordinates are taken."""
    by_woj: dict[str, list[dict[str, str]]] = {}
    for c in communes:
        if c["teryt"][-1] in {"2", "3"}:
            by_woj.setdefault(c["wojewodztwo"], []).append(c)
    names = sorted(by_woj)
    per = total // len(names)
    sample: list[dict] = []
    for name, size in zip(names, quotas(len(names), per, total), strict=True):
        pool = sorted(by_woj[name], key=lambda c: c["teryt"])
        random.Random(f"{seed}-{name}").shuffle(pool)
        picked: list[dict] = []
        for c in pool:
            if len(picked) == size:
                break
            lonlat = geocode(client, c)
            if lonlat:
                picked.append({**c, "lon": lonlat[0], "lat": lonlat[1]})
        print(name, len(picked), file=sys.stderr)
        sample += picked
    return sample


def assign_sets(sample: list[dict], dev_total: int = DEV_TOTAL) -> None:
    """Every voivodeship gives `dev_total // 16` development communes, the first ones give one more."""
    names = sorted({c["wojewodztwo"] for c in sample})
    for name, n_dev in zip(names, quotas(len(names), dev_total // len(names), dev_total), strict=True):
        members = [c for c in sample if c["wojewodztwo"] == name]
        for i, c in enumerate(members):
            c["zbior"] = "dev" if i < n_dev else "test"


def write(sample: list[dict], path: Path = OUT_PATH) -> None:
    sample.sort(key=lambda c: (c["wojewodztwo"], c["teryt"]))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sample)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--total", type=int, default=200)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args(argv)
    with httpx.Client(
        headers={"User-Agent": "susza-raport/0.1 (research sample)"}, follow_redirects=True
    ) as client:
        communes = list_communes(client)
        print(len(communes), "communes in the SMSR selectors", file=sys.stderr)
        sample = draw(communes, client, args.total, args.seed)
    assign_sets(sample)
    write(sample)
    print(f"{len(sample)} communes -> {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
