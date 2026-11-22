"""Golden locations: hand-picked parcels with expert expectations, checked in categories.

Two modes:
- offline (default): the 12 frozen parcels of demo/data/locations/ through the TestClient, no network, fast (CI);
- `--base-url https://ADDRESS` (or GOLDEN_BASE_URL): the same checks over HTTP against a running application with
  live data; locations without a frozen copy (and the two added from parcels50.csv) run only in this mode.

The expectations come from independent knowledge (Dz.U. 2019 poz. 739, SMSR of the commune, IMGW weather, IUNG slope
classes), not from the current output. Where the application differs from the expert expectation the check is
marked xfail (strict=False) in `known_defects` of expectations.json with the reason and the package that fixes it.
Categories (the first part of the check id): verdict, causes, actions, retention, text, perf, negative.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "expectations.json").read_text(encoding="utf-8"))
DEFAULTS = DATA["defaults"]
LOCS = {loc["id"]: loc for loc in DATA["locations"]}
FROZEN_ROOT = HERE.parents[1] / "demo" / "data" / "locations"

BADGE_BELOW = "Bilans poniżej progu suszy (szacunek dla działki)"
BADGE_ABOVE = "Bilans jest lepszy niż próg suszy (szacunek dla działki)"
CAUSE_CODES = ("malo_opadu", "duze_parowanie", "gleba_lekka", "splyw", "faza_wrazliwa")
SOURCE_LINE = re.compile(r"^.+·\s*(s\.|art\.)\s*\d+.*·\s*\S+")
DATE_DO = re.compile(r"do\s+(\d{1,2})\.(\d{1,2})\.(\d{4})")

pytestmark = pytest.mark.golden


# ---- fetching: one place that knows offline vs live -----------------------------------------------------------


class Fetched:
    """What one location gave: the report as a dict, the page texts and the times."""

    def __init__(self, loc: dict) -> None:
        self.loc = loc
        self.report: dict = {}
        self.cold_s = 0.0
        self.warm_s = 0.0
        self.print_s = 0.0
        self.texts: dict[str, str] = {}
        self.error = ""
        self.live = False
        self.outline_2180: list[list[float]] | None = None

    @property
    def day(self) -> date:
        return date.fromisoformat(self.loc["day"])

    def actions(self) -> list[dict]:
        found = [a for s in self.report.get("sections", []) for a in s.get("actions", [])]
        return sorted(found, key=lambda a: a["n"])

    def causes(self) -> list[dict]:
        return self.report.get("diagnosis", {}).get("causes", [])

    def text(self) -> str:
        return " ".join(self.texts.values())


_CACHE: dict[tuple[str, str], Fetched] = {}


def _query(loc: dict, parcel_id: str) -> str:
    return urlencode({"dzialka": parcel_id, "data": loc["day"], "uprawa": loc["crop"]})


def _visible(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    page = re.sub(r"<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", page.replace("&nbsp;", " ").replace("\xa0", " "))


def _resolve_parcel(client: httpx.Client, xy: list[float]) -> str | None:
    try:
        r = client.get(
            "https://uldk.gugik.gov.pl/",
            params={"request": "GetParcelByXY", "xy": f"{xy[0]},{xy[1]},4326", "result": "teryt"},
            timeout=20,
        )
        line = r.text.replace("\r", "").split("\n")
        return line[1].split("|")[0] if len(line) > 1 and "|" in line[1] else None
    except httpx.HTTPError:
        return None


def _fetch_live(loc: dict, base: str) -> Fetched:
    out = Fetched(loc)
    out.live = True
    with httpx.Client(base_url=base.rstrip("/"), timeout=180, follow_redirects=True) as client:
        parcel_id = loc["parcel_id"] or _resolve_parcel(client, loc["xy"])
        if not parcel_id:
            out.error = "nie udalo sie ustalic numeru dzialki (ULDK)"
            return out
        q = _query(loc, parcel_id)
        started = time.perf_counter()
        r = client.get(f"/api/raport?{q}")
        out.cold_s = time.perf_counter() - started
        if r.status_code != 200:
            out.error = f"/api/raport: HTTP {r.status_code}: {r.text[:200]}"
            return out
        out.report = r.json()
        started = time.perf_counter()
        client.get(f"/api/raport?{q}")
        out.warm_s = time.perf_counter() - started
        started = time.perf_counter()
        r = client.get(f"/raport/druk?{q}")
        out.print_s = time.perf_counter() - started
        out.texts["druk"] = _visible(r.text)
        r = client.get(f"/raport?{q}")
        page = _visible(r.text)
        if "liczę" not in page.lower()[:2000]:  # the waiting page is not the report
            out.texts["rolnik"] = page
    return out


def _fetch_offline(loc: dict) -> Fetched:
    from fastapi.testclient import TestClient

    from app.crop_condition import background
    from app.geodata import config, load_sample
    from app.main import app
    from app.smsr import pages
    from app.soil import iung

    out = Fetched(loc)
    folder = FROZEN_ROOT / loc["frozen"]
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("GEODATA_OFFLINE", "1")
        config.set_offline(True)
        mp.setattr(config, "demo_dir", lambda: folder / "geodata")
        mp.setattr(iung, "frozen_dir", lambda: folder / "soil")
        mp.setattr(background, "frozen_dir", lambda: folder / "satellite")
        mp.setattr(pages, "DEMO_DIR", folder / "smsr")
        mp.setattr(pages, "CACHE_DIR", folder / "no_cache")
        mp.setattr(pages, "ARCHIVE_DIR", folder / "no_archive")
        client = TestClient(app)
        q = _query(loc, loc["parcel_id"])
        started = time.perf_counter()
        r = client.get(f"/api/raport?{q}")
        out.cold_s = time.perf_counter() - started
        if r.status_code != 200:
            out.error = f"/api/raport: HTTP {r.status_code}: {r.text[:200]}"
            return out
        out.report = r.json()
        started = time.perf_counter()
        client.get(f"/api/raport?{q}")
        out.warm_s = time.perf_counter() - started
        started = time.perf_counter()
        r = client.get(f"/raport/druk?{q}")
        out.print_s = time.perf_counter() - started
        out.texts["druk"] = _visible(r.text)
        out.texts["rolnik"] = _visible(client.get(f"/raport?{q}").text)
        out.texts["doradca"] = _visible(client.get(f"/raport?{q}&widok=doradca").text)
        sample = load_sample(loc["parcel_id"], loc["day"], folder / "geodata")
        if sample is not None and sample.parcel.usable:
            out.outline_2180 = sample.parcel.data.rings_2180[0]
        config.set_offline(None)
    return out


def fetched(loc_id: str, base_url: str | None) -> Fetched:
    key = (loc_id, base_url or "")
    if key not in _CACHE:
        loc = LOCS[loc_id]
        _CACHE[key] = _fetch_live(loc, base_url) if base_url else _fetch_offline(loc)
    return _CACHE[key]


# ---- helpers ---------------------------------------------------------------------------------------------------


def _period_end(f: Fetched) -> date | None:
    p = f.report["verdict"].get("period")
    return date.fromisoformat(p["end"]) if p else None


def _inside(x: float, y: float, ring: list[list[float]], tolerance_m: float = 2.0) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        (x1, y1), (x2, y2) = ring[i][:2], ring[(i + 1) % n][:2]
        dx, dy = x2 - x1, y2 - y1
        length2 = dx * dx + dy * dy
        t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length2))
        if (x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2 <= tolerance_m**2:
            return True
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * dx / (y2 - y1):
            inside = not inside
    return inside


def _slope(f: Fetched) -> float | None:
    return f.report.get("vulnerability", {}).get("slope_pct")


def _num(s: str) -> float:
    return float(s.replace(" ", "").replace("\xa0", "").replace(",", "."))


def _candidates(f: Fetched) -> list[dict]:
    return [a["candidate"] for a in f.actions() if a.get("candidate")]


# ---- checks: verdict (a) ---------------------------------------------------------------------------------------


def check_verdict_direction(f: Fetched, exp: dict) -> None:
    v = f.report["verdict"]
    want = exp["verdict"]["direction"]
    state, margin = v["state"], v["margin_mm"]
    if want == "any":
        assert state != "no_data", state
    elif want == "susza":
        assert state == "below" and margin is not None and margin < 0, (state, margin)
    elif want == "brak":
        assert state == "above" and margin is not None and margin >= 0, (state, margin)
    elif want == "poza_sezonem":
        assert state == "out_of_season", state
    else:
        assert state == {"running": "running", "no_threshold": "no_threshold"}[want], state
    assert v["badge"] != "undefined" and "None" not in v["badge"]


def check_verdict_margin(f: Fetched, exp: dict) -> None:
    v = f.report["verdict"]
    rng = exp["verdict"].get("margin_range")
    if exp["verdict"]["direction"] in ("running", "no_threshold"):
        assert v["margin_mm"] is None, f"margines {v['margin_mm']} mimo braku werdyktu"
    elif rng:
        assert v["margin_mm"] is not None and rng[0] <= v["margin_mm"] <= rng[1], (v["margin_mm"], rng)
    thr = exp["verdict"].get("threshold_range")
    if thr:
        assert v["threshold_mm"] is not None and thr[0] <= v["threshold_mm"] <= thr[1], (v["threshold_mm"], thr)
    if not rng and not thr and exp["verdict"]["direction"] not in ("running", "no_threshold"):
        pytest.skip("brak oczekiwania recznego")


def check_verdict_balance(f: Fetched, exp: dict) -> None:
    rng = exp["verdict"].get("kbw_range")
    if not rng:
        pytest.skip("brak oczekiwania recznego")
    kbw = f.report["verdict"]["kbw_mm"]
    assert kbw is not None and rng[0] <= kbw <= rng[1], (kbw, rng)


def check_verdict_smsr(f: Fetched, exp: dict) -> None:
    want = exp["verdict"].get("smsr", "any")
    if want == "any":
        pytest.skip("brak oczekiwania recznego")
    s = f.report.get("smsr") or {}
    v = f.report["verdict"]
    if want == "brak":
        assert s.get("state") != "ok", f"SMSR jest ({s.get('symbol')}), a oczekiwano braku porownania"
        assert s.get("reason", "").startswith("Brak"), s.get("reason")
        return
    assert s.get("state") == "ok", s.get("reason")
    drought = s.get("symbol") == "+"
    margin = v["margin_mm"]
    assert margin is not None
    below = margin < 0
    if abs(margin) <= 15:  # at the threshold both answers are acceptable
        return
    assert drought == below, f"SMSR {'susza' if drought else 'brak suszy'}, bilans {margin:+.0f} mm"


def check_verdict_window(f: Fetched, exp: dict) -> None:
    v = f.report["verdict"]
    p = v.get("period")
    day = f.day
    assert p is not None
    start, end = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
    assert start < end
    if v["state"] == "out_of_season":
        assert v["season_year"] is not None and v["season_year"] <= day.year
        assert end <= day
        assert date(v["season_year"], 3, 21) <= start and end <= date(v["season_year"], 9, 30)
    elif v["state"] == "running":
        assert start <= day <= end and not p["complete"]
        assert (day - start).days + 1 - p["days"] <= DEFAULTS["max_window_lag_days"]
    else:
        assert p["complete"] and end <= day
        assert (day - end).days <= exp["verdict"].get("max_lag_days", DEFAULTS["max_window_lag_days"]), f"okno konczy sie {end}, data {day}"
        assert 59 <= (end - start).days + 1 <= 62


# ---- causes (b) -----------------------------------------------------------------------------------------------


def check_causes_required(f: Fetched, exp: dict) -> None:
    need = exp["causes"].get("required", [])
    if not need:
        pytest.skip("brak oczekiwania recznego")
    got = {c["code"] for c in f.causes()}
    assert set(need) <= got, f"brak przyczyn {sorted(set(need) - got)}, sa {sorted(got)}"


def check_causes_forbidden(f: Fetched, exp: dict) -> None:
    ban = exp["causes"].get("forbidden", [])
    if not ban:
        pytest.skip("brak oczekiwania recznego")
    got = {c["code"] for c in f.causes()}
    why = exp["causes"].get("forbidden_why", {})
    bad = sorted(set(ban) & got)
    assert not bad, "; ".join(f"{b}: {why.get(b, '')}" for b in bad)


# ---- actions (c) -----------------------------------------------------------------------------------------------


def check_actions_required(f: Fetched, exp: dict) -> None:
    req = exp["actions"].get("required", [])
    if not req:
        pytest.skip("brak oczekiwania recznego")
    acts = f.actions()
    missing = []
    for r in req:
        hit = [a for a in acts if any(k in a["id"] for k in r["any"])]
        if r.get("title_re"):
            hit = [a for a in hit if re.search(r["title_re"], a["title"])]
        if not hit:
            missing.append(f"{'/'.join(r['any'])} ({r['why']})")
    assert not missing, "brak dzialan: " + "; ".join(missing)


def check_actions_forbidden(f: Fetched, exp: dict) -> None:
    ids = [i for i in DEFAULTS["forbidden_action_ids"] if i not in exp["actions"].get("allow_ids", [])]
    rules = [{"id_re": f"^{re.escape(i)}$", "why": "regulator drenow bez drenow w danych"} for i in ids]
    rules += exp["actions"].get("forbidden", [])
    bad = []
    for a in f.actions():
        for r in rules:
            if (not r.get("id_re") or re.search(r["id_re"], a["id"])) and (
                not r.get("title_re") or re.search(r["title_re"], a["title"])
            ):
                bad.append(f"{a['id']} ({r['why']})")
    assert not bad, "zakazane dzialania: " + "; ".join(bad)


def check_actions_max(f: Fetched, exp: dict) -> None:
    limit = exp["actions"].get("max") or DEFAULTS["max_actions"]
    assert len(f.actions()) <= limit, f"{len(f.actions())} dzialan, max {limit}"
    numbers = [a["n"] for a in f.actions()]
    assert numbers == list(range(1, len(numbers) + 1)), numbers


def check_actions_cause_link(f: Fetched, exp: dict) -> None:
    known = {c["code"] for c in f.causes()}
    bad = []
    for a in f.actions():
        if not (a.get("cause_codes") or a.get("causes")):
            bad.append(f"{a['id']}: brak powiazanej przyczyny")
        elif a.get("cause_codes") and not set(a["cause_codes"]) <= known:
            bad.append(f"{a['id']}: przyczyna spoza rozpoznanych")
    assert not bad, "; ".join(bad)


# ---- retention (d) ---------------------------------------------------------------------------------------------


def check_retention_slope(f: Fetched, exp: dict) -> None:
    r = exp["retention"]
    slope = _slope(f)
    sane = r.get("slope_max_sane")
    if sane is not None:
        assert slope is None or slope <= sane, f"spadek {slope}% nieprawdopodobny"
    rng = r.get("slope_range")
    if not rng:
        pytest.skip("brak oczekiwania recznego")
    assert slope is not None and rng[0] <= slope <= rng[1], (slope, rng)


def check_retention_flat(f: Fetched, exp: dict) -> None:
    if exp["retention"]["kind"] != "flat":
        pytest.skip("nie dotyczy (dzialka nie jest plaska)")
    markers = f.report.get("map", {}).get("markers", [])
    cands = [c for c in _candidates(f) if c.get("geometry")]
    assert not markers and not cands, f"plaska dzialka ma pinezki: {[m['kind'] for m in markers]}"
    text = f.text().lower()
    assert re.search(r"płask\w*[^.]{0,80}(nie spływa|nie ucieka|zostaje|zatrzymuje)", text), (
        "brak zdania, ze dzialka jest plaska i woda nie splywa"
    )
    assert "za mały" not in text and "nie można wskazać" not in text


def check_retention_candidates(f: Fetched, exp: dict) -> None:
    r = exp["retention"]
    if r["kind"] != "slope":
        pytest.skip("nie dotyczy")
    cands = _candidates(f)
    if r.get("candidate_or_reason"):
        acts = [a for a in f.actions() if a["group"] == "retencja"]
        for a in acts:
            if a.get("place") is None:
                assert a["no_place_reason"].startswith("brak miejsca na działce, bo "), a["id"]
        for c in cands:
            if not c.get("geometry"):
                assert c["no_place_reason"].startswith("brak miejsca na działce, bo "), c["action_id"]
        assert acts, "brak dzialania retencyjnego ani powodu"
        return
    assert len(cands) >= r.get("min_candidates", 1), f"{len(cands)} kandydatow, oczekiwano >= {r.get('min_candidates', 1)}"
    need = r.get("required_any", [])
    ids = [c["action_id"] or "" for c in cands] + [a["id"] for a in f.actions()]
    assert not need or any(k in i for k in need for i in ids), f"brak kandydata z {need}; sa {ids}"


def check_retention_geometry(f: Fetched, exp: dict) -> None:
    geoms = [c for c in _candidates(f) if c.get("geometry")]
    if not geoms:
        pytest.skip("brak kandydatow z geometria")
    if f.outline_2180 is None:
        pytest.skip("brak obrysu (tryb zywy)")
    for c in geoms:
        assert all(_inside(x, y, f.outline_2180) for x, y in c["geometry"]["coordinates"]), c["action_id"]


def check_retention_pins(f: Fetched, exp: dict) -> None:
    markers = f.report.get("map", {}).get("markers", [])
    numbers = sorted(m["n"] for m in markers)
    assert numbers == list(range(1, len(numbers) + 1)), f"numeracja pinezek nieciagla: {numbers}"
    assert len(numbers) <= 3, f"{len(numbers)} pinezek na mapie (max 3)"
    action_numbers = {a["n"] for a in f.actions()}
    assert set(numbers) <= action_numbers, "pinezka bez dzialania o tym numerze"


def check_retention_fields(f: Fetched, exp: dict) -> None:
    cands = _candidates(f)
    if not cands:
        pytest.skip("brak kandydatow")
    bad = []
    for c in cands:
        if not c.get("risks"):
            bad.append(f"{c['action_id']}: brak ryzyka")
        if not c.get("legal"):
            bad.append(f"{c['action_id']}: brak formalnosci")
        if not c.get("next_step"):
            bad.append(f"{c['action_id']}: brak nastepnego kroku")
    assert not bad, "; ".join(bad)


# ---- text quality (e) ------------------------------------------------------------------------------------------


def check_text_source(f: Fetched, exp: dict) -> None:
    bad = [f"{a['id']}: «{a['source']}»" for a in f.actions() if not SOURCE_LINE.search(a.get("source", ""))]
    assert not bad, "zrodlo bez dokumentu, strony i rodzaju dowodu: " + "; ".join(bad)


def check_text_risk(f: Fetched, exp: dict) -> None:
    text = f.texts.get("druk") or f.text()
    n = len(f.actions())
    risk = len(re.findall(r"ryzyko:", text, flags=re.I))
    notwhen = len(re.findall(r"nie stosuj, gdy", text, flags=re.I))
    assert risk >= n and notwhen >= n, f"{n} dzialan, linii «Ryzyko:» {risk}, «Nie stosuj, gdy» {notwhen}"


def check_text_area(f: Fetched, exp: dict) -> None:
    area = f.report["parcel"]["area_ha"]
    bad = []
    for a in f.actions():
        for m in re.finditer(r"(?:na|działkę|dla)\s+(\d[\d\s\xa0]*(?:,\d+)?)\s*ha\b", a["sentence"]):
            value = _num(m.group(1))
            if abs(value - area) > max(0.01 * area, 0.006):  # 1%, and the rounding of the printed value
                bad.append(f"{a['id']}: {value} ha, dzialka {area:.2f} ha")
    assert not bad, "; ".join(bad)


def check_text_due_dates(f: Fetched, exp: dict) -> None:
    day = f.day
    bad = []
    for a in f.actions():
        dates = [a["due"] and date.fromisoformat(a["due"])] + [
            date(int(y), int(m), int(d)) for d, m, y in DATE_DO.findall(a["when"] + " " + a["sentence"])
        ]
        for d in (x for x in dates if x):
            if d < day:
                bad.append(f"{a['id']}: termin {d} przed data oceny {day}")
            elif d > day + timedelta(days=500):
                bad.append(f"{a['id']}: termin {d} za daleko")
            elif not 3 <= d.month <= 11:
                bad.append(f"{a['id']}: termin {d} poza sezonem prac")
        if a["when"].startswith("Brak:") or "jeszcze nie wyliczamy" in a["when"]:
            bad.append(f"{a['id']}: termin to komunikat o braku")
    assert not bad, "; ".join(bad)


def check_text_forbidden_words(f: Fetched, exp: dict) -> None:
    bad = []
    for name, text in f.texts.items():
        low = text.lower()
        for w in DEFAULTS["forbidden_words"]:
            hit = re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text) if w in ("None", "NaN", "TODO", "undefined") else (
                w.lower() in low
            )
            if hit and not (name == "doradca" and w in CAUSE_CODES):
                bad.append(f"{name}: «{w}»")
        for rx in DEFAULTS["forbidden_word_regex"]:
            if re.search(rx, text, flags=re.I):
                bad.append(f"{name}: /{rx}/")
    assert not bad, "; ".join(bad)


def check_text_no_frozen_copy_online(f: Fetched, exp: dict) -> None:
    """Online (--base-url) the report counts live: no label "kopia z dnia/danych" (task 3.3.4: no ready-made answers)."""
    if not f.live:
        return
    bad = [f"{name}: «{m.group(0)}»" for name, text in f.texts.items() for m in re.finditer(r"kopia (?:z dnia|danych z)[^.\n]{0,20}", text, flags=re.I)]
    assert not bad, "; ".join(bad[:6])


def check_text_contradictions(f: Fetched, exp: dict) -> None:
    text = f.text().lower()
    bad = []
    if "nie jest wyznaczony" in text and "teren jest nachylony" in text:
        bad.append("«spadek nie jest wyznaczony» razem z «Teren jest nachylony»")
    if _slope(f) is not None and "spadek działki nie jest wyznaczony" in text:
        bad.append(f"«spadek działki nie jest wyznaczony» mimo spadku {_slope(f)}%")
    sentences = " ".join(a["sentence"] for a in f.actions())
    ranges = [(_num(a), _num(b)) for a, b in re.findall(r"Dawka:\s*(\d+)[–-](\d+)\s*mm", sentences)]
    single = [_num(x) for x in re.findall(r"około\s+(\d+)\s*mm na polew", sentences)]
    for s in single:
        for lo, hi in ranges:
            if not lo <= s <= hi:
                bad.append(f"dawka {s:.0f} mm poza zakresem {lo:.0f}–{hi:.0f} mm")
    kbw = f.report["verdict"].get("kbw_mm")
    for m in re.finditer(r"niedoborze\s+(\d+)\s*mm", sentences):
        if f.report["verdict"]["state"] in ("above", "out_of_season") and (f.report["verdict"]["margin_mm"] or 0) >= 0:
            bad.append(f"«niedobór {m.group(1)} mm» to bilans, a prog nie jest przekroczony (bilans {kbw})")
            break
    assert not bad, "; ".join(bad)


def check_text_one_number(f: Fetched, exp: dict) -> None:
    vuln = f.report.get("vulnerability", {})
    if vuln.get("k") is None:
        pytest.skip("brak liczby sezonow")
    sections = {s["id"]: s for s in f.report.get("sections", [])}
    sentences = " ".join(sections.get("uprawa", {}).get("sentences", []))
    label_hits = re.findall(r"(?:zboża jare|zboża ozime|rzepak i rzepik|kukurydza\w*|rośliny strączkowe|drzewa owocowe|chmiel)\s+w\s+(\d+)\s+z\s+(\d+)", sentences)
    bad = []
    forecast = f.report.get("forecast", {})
    for k, n in label_hits[:1]:
        if int(k) != vuln["k"] or int(n) != vuln["n"]:
            bad.append(f"podatnosc {vuln['k']} z {vuln['n']}, sekcja uprawy {k} z {n}")
    if forecast.get("state") == "ok" and forecast.get("method") == "historical" and forecast.get("n"):
        if forecast["n"] != vuln["n"]:
            bad.append(f"klimatologia z {forecast['n']} lat, podatnosc z {vuln['n']} sezonow")
    assert not bad, "; ".join(bad)


# ---- performance (f) -------------------------------------------------------------------------------------------


def check_perf_cold(f: Fetched, exp: dict) -> None:
    limit = DEFAULTS["max_report_cold_s"] if f.loc.get("_live") else DEFAULTS["max_offline_build_s"]
    assert f.cold_s < limit, f"{f.cold_s:.1f} s (limit {limit} s)"


def check_perf_warm(f: Fetched, exp: dict) -> None:
    assert f.warm_s < DEFAULTS["max_report_warm_s"], f"{f.warm_s:.1f} s"


def check_perf_print(f: Fetched, exp: dict) -> None:
    assert f.print_s < DEFAULTS["max_print_s"], f"{f.print_s:.1f} s"


# ---- negative controls (g) -------------------------------------------------------------------------------------


def check_negative(f: Fetched, exp: dict) -> None:
    kind = exp.get("negative")
    v = f.report["verdict"]
    acts = f.actions()
    if kind is None:
        pytest.skip("nie dotyczy")
    if kind == "wet_year":
        assert v["state"] == "above" and v["badge"] != BADGE_BELOW, (v["state"], v["badge"])
        assert not [a["title"] for a in acts if a["title"].startswith("Teraz tak")], "rada 'nawadniaj' przy marginesie dodatnim"
        assert "susza: tak" not in f.text().lower()
    elif kind == "out_of_season":
        assert v["state"] == "out_of_season"
        assert v["badge"] not in (BADGE_BELOW, BADGE_ABOVE), v["badge"]
        assert re.search(r"poza sezonem|poza okresem|nie oceniamy", f.text().lower()), "brak komunikatu o sezonie"
        assert f.report.get("off_season"), "brak podsumowania poza sezonem"
        assert not [a["title"] for a in acts if a["title"].startswith("Teraz tak")]
    elif kind == "running":
        assert v["state"] == "running" and v["badge"] == "", (v["state"], v["badge"])
        assert re.search(r"jeszcze trwa|po 2\d\.\d\d", (v["sentence"] + v["note"]).lower()), "brak komunikatu o trwajacym okresie"
        assert v["margin_mm"] is None
    elif kind == "no_threshold":
        assert v["state"] == "no_threshold" and v["badge"] not in (BADGE_BELOW, BADGE_ABOVE)
        assert "nie ma progu" in v["sentence"].lower(), v["sentence"]
        assert not [a["title"] for a in acts if a["title"].startswith("Teraz tak")]


CHECKS = {
    "verdict.direction": check_verdict_direction,
    "verdict.margin": check_verdict_margin,
    "verdict.balance": check_verdict_balance,
    "verdict.smsr": check_verdict_smsr,
    "verdict.window": check_verdict_window,
    "causes.required": check_causes_required,
    "causes.forbidden": check_causes_forbidden,
    "actions.required": check_actions_required,
    "actions.forbidden": check_actions_forbidden,
    "actions.max": check_actions_max,
    "actions.cause_link": check_actions_cause_link,
    "retention.slope": check_retention_slope,
    "retention.flat": check_retention_flat,
    "retention.candidates": check_retention_candidates,
    "retention.geometry": check_retention_geometry,
    "retention.pins": check_retention_pins,
    "retention.fields": check_retention_fields,
    "text.source": check_text_source,
    "text.risk": check_text_risk,
    "text.area": check_text_area,
    "text.due_dates": check_text_due_dates,
    "text.forbidden_words": check_text_forbidden_words,
    "text.no_frozen_copy_online": check_text_no_frozen_copy_online,
    "text.contradictions": check_text_contradictions,
    "text.one_number": check_text_one_number,
    "perf.cold": check_perf_cold,
    "perf.warm": check_perf_warm,
    "perf.print": check_perf_print,
    "negative.control": check_negative,
}


def _defect(loc_id: str, check: str) -> dict | None:
    for d in DATA["known_defects"]:
        locs = d["loc"] if isinstance(d["loc"], list) else [d["loc"]]
        checks = d["check"] if isinstance(d["check"], list) else [d["check"]]
        if (loc_id in locs or "*" in locs) and check in checks:
            return d
    return None


def _params() -> list:
    out = []
    for loc_id in LOCS:
        for check in CHECKS:
            marks: list = []
            d = _defect(loc_id, check)
            if d:
                marks.append(
                    pytest.mark.xfail(reason=f"{d['priority']} {d['owner']}: {d['reason']}", strict=False)
                )
            out.append(pytest.param(loc_id, check, marks=marks, id=f"{loc_id}@{check}"))
    return out


@pytest.mark.parametrize(("loc_id", "check"), _params())
def test_golden(loc_id: str, check: str, request: pytest.FixtureRequest) -> None:
    base = request.config.getoption("--base-url", default=None)
    only = request.config.getoption("--golden-only", default=None)
    if only and only != loc_id:
        pytest.skip(f"wybrano tylko {only}")
    loc = LOCS[loc_id]
    if not base and not loc["frozen"]:
        pytest.skip("brak zamrozonej kopii danych: tylko z --base-url")
    f = fetched(loc_id, base)
    f.loc["_live"] = bool(base)
    assert not f.error, f.error
    CHECKS[check](f, loc)


def test_expectations_are_well_formed() -> None:
    """The set differs enough: 10-12 frozen locations, every expectation names a reason, defects name an owner."""
    frozen = [loc for loc in LOCS.values() if loc["frozen"]]
    assert 10 <= len(frozen) <= 12 and len(LOCS) >= 13
    index = {loc["name"]: loc for loc in json.loads((FROZEN_ROOT / "index.json").read_text(encoding="utf-8"))}
    for loc in LOCS.values():
        assert loc["why"] and loc["expert_basis"], loc["id"]
        assert loc["frozen"] is None or loc["frozen"] in index
        if loc["frozen"]:
            for k in ("parcel_id", "day", "crop"):
                assert loc[k] == index[loc["frozen"]][k], (loc["id"], k)
        else:
            assert loc["parcel_id"] or loc.get("xy"), loc["id"]
    for d in DATA["known_defects"]:
        assert d["owner"] and d["priority"] in ("P1", "P2", "P3") and d["reason"], d
        for check in d["check"] if isinstance(d["check"], list) else [d["check"]]:
            assert check in CHECKS, check
