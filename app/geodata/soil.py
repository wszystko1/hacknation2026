"""Topsoil texture (sand / silt / clay, 0-30 cm) from ISRIC SoilGrids 2.0 with an explicit "no data" result.

SoilGrids is slow (2-5 s) and returns null for some points (built-up areas, water). Neither case is an
error for the caller: the result then has status `fallback`, empty values and a note. No number is invented.
"""

from __future__ import annotations

from dataclasses import asdict

from . import cache, config, http
from .errors import CacheMiss, GeodataError, UpstreamError
from .models import Soil, SourceResult, now_iso

RESOLUTION = "SoilGrids 2.0, 250 m grid, global model (not the Polish soil-agricultural map)"
_DEPTHS = {"0-5cm": 5.0, "5-15cm": 10.0, "15-30cm": 15.0}


def usda_texture_class(sand: float, silt: float, clay: float) -> str:
    """USDA soil texture triangle (percentages by weight)."""
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 2 * clay < 30:
        return "loamy sand"
    if (7 <= clay < 20 and sand > 52 and silt + 2 * clay >= 30) or (
        clay < 7 and silt < 50 and silt + 2 * clay >= 30
    ):
        return "sandy loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "loam"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "silt loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "sandy clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "clay loam"
    if 27 <= clay < 40 and sand <= 20:
        return "silty clay loam"
    if clay >= 35 and sand > 45:
        return "sandy clay"
    if clay >= 40 and silt >= 40:
        return "silty clay"
    return "clay"


def parse_soilgrids(payload: dict) -> Soil:
    """Thickness-weighted 0-30 cm means; Soil(available=False) when any fraction is null."""
    values: dict[str, float | None] = {}
    try:
        layers = payload["properties"]["layers"]
    except (KeyError, TypeError) as exc:
        raise UpstreamError(f"SoilGrids: unexpected answer: {str(payload)[:160]}") from exc
    for layer in layers:
        factor = float(layer.get("unit_measure", {}).get("d_factor", 10) or 10)
        total = weight = 0.0
        for depth in layer.get("depths", []):
            mean = (depth.get("values") or {}).get("mean")
            thickness = _DEPTHS.get(depth.get("label"))
            if mean is not None and thickness:
                total += mean / factor * thickness
                weight += thickness
        values[layer.get("name")] = round(total / weight, 1) if weight else None
    sand, silt, clay = values.get("sand"), values.get("silt"), values.get("clay")
    if sand is None or silt is None or clay is None:
        return Soil(None, None, None, None, available=False)
    return Soil(sand, silt, clay, usda_texture_class(sand, silt, clay), available=True)


def _no_data(note: str, url: str = config.SOILGRIDS_URL, from_cache: bool = False) -> SourceResult[Soil]:
    return SourceResult(
        "soil", "fallback", Soil(None, None, None, None, available=False), source_url=url, retrieved_at=now_iso(),
        resolution=RESOLUTION, notes=[note, "no soil texture: use a neutral soil category and say so in the report"],
        from_cache=from_cache,
    )  # fmt: skip


def fetch_soil(
    lat: float, lon: float, *, timeout: float | None = None, deadline: float | None = None
) -> SourceResult[Soil]:
    """Texture for the point. Never raises for slow or empty answers (status `fallback`); raises CacheMiss offline."""
    key = f"{lat:.3f}_{lon:.3f}"
    hit = cache.get_json("soil", key)
    if hit is not None and not hit["data"]["available"]:
        hit = cache.get_json("soil", key, config.TTL_SOIL_NULL)  # empty answers are re-checked after a day
    if hit is not None:
        soil = Soil(**hit["data"])
        if not soil.available:
            return _no_data("SoilGrids has no value for this point (cached answer)", hit["url"], True)
        return SourceResult(
            "soil", "ok", soil, source_url=hit["url"], retrieved_at=hit["retrieved_at"], resolution=RESOLUTION,
            from_cache=True,
        )  # fmt: skip
    cache.require_online("soil", key)
    params = [("lon", f"{lon:.5f}"), ("lat", f"{lat:.5f}"), ("value", "mean")]
    params += [("property", p) for p in ("sand", "silt", "clay")] + [("depth", d) for d in _DEPTHS]
    try:
        resp = http.get(
            config.SOILGRIDS_URL,
            params=params,
            timeout=timeout or config.TIMEOUTS["soil"],
            retries=0,
            deadline=deadline,
        )
        if resp.status_code != 200:
            raise UpstreamError(f"SoilGrids HTTP {resp.status_code}: {resp.text[:120]}")
        soil = parse_soilgrids(resp.json())
    except CacheMiss:
        raise
    except (GeodataError, ValueError) as exc:
        return _no_data(f"SoilGrids unavailable: {exc}")
    entry = {"data": asdict(soil), "url": str(resp.url), "retrieved_at": now_iso()}
    cache.put_json("soil", key, entry)
    if not soil.available:
        return _no_data("SoilGrids returned null for this point", entry["url"])
    return SourceResult(
        "soil", "ok", soil, source_url=entry["url"], retrieved_at=entry["retrieved_at"], resolution=RESOLUTION
    )
