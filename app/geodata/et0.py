"""FAO-56 Penman-Monteith reference evapotranspiration from daily values (Allen et al. 1998)."""

from __future__ import annotations

import numpy as np


def extraterrestrial(day_of_year: np.ndarray, latitude_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Extraterrestrial radiation Ra [MJ/m2/day] and maximum daylight hours N."""
    phi = np.radians(latitude_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * day_of_year / 365.0)
    decl = 0.409 * np.sin(2 * np.pi * day_of_year / 365.0 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(decl), -1, 1))
    ra = (
        24
        * 60
        / np.pi
        * 0.0820
        * dr
        * (ws * np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.sin(ws))
    )
    return ra, 24.0 / np.pi * ws


def radiation_from_sunshine(
    sunshine_h: np.ndarray, day_of_year: np.ndarray, latitude_deg: float
) -> np.ndarray:
    """Solar radiation Rs from sunshine duration (Angstrom formula, FAO-56 eq. 35, a=0.25, b=0.5)."""
    ra, daylight = extraterrestrial(day_of_year, latitude_deg)
    return (0.25 + 0.5 * np.clip(sunshine_h / daylight, 0, 1)) * ra


def et0_penman_monteith(
    tmax: np.ndarray, tmin: np.ndarray, rh_mean: np.ndarray, wind_2m: np.ndarray, rs_mj: np.ndarray,
    day_of_year: np.ndarray, latitude_deg: float, elevation_m: float,
) -> np.ndarray:  # fmt: skip
    """ET0 [mm/day]. Inputs: temperatures in deg C, mean relative humidity in %, wind at 2 m in m/s, Rs in MJ/m2/day."""
    tmean = (tmax + tmin) / 2.0

    def e0(t: np.ndarray) -> np.ndarray:
        return 0.6108 * np.exp(17.27 * t / (t + 237.3))

    pressure = 101.3 * ((293.0 - 0.0065 * elevation_m) / 293.0) ** 5.26
    gamma = 0.000665 * pressure
    es = (e0(tmax) + e0(tmin)) / 2.0
    ea = np.clip(rh_mean, 0, 100) / 100.0 * es
    delta = 4098.0 * e0(tmean) / (tmean + 237.3) ** 2
    ra, _ = extraterrestrial(day_of_year, latitude_deg)
    rso = (0.75 + 2e-5 * elevation_m) * ra
    rns = 0.77 * rs_mj
    ratio = np.clip(np.divide(rs_mj, rso, out=np.ones_like(rs_mj), where=rso > 0), 0.25, 1.0)
    rnl = (
        4.903e-9 * ((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2.0
        * (0.34 - 0.14 * np.sqrt(np.maximum(ea, 0))) * (1.35 * ratio - 0.35)
    )  # fmt: skip
    rn = rns - rnl
    et0 = (0.408 * delta * rn + gamma * 900.0 / (tmean + 273.0) * wind_2m * (es - ea)) / (
        delta + gamma * (1 + 0.34 * wind_2m)
    )
    return np.maximum(et0, 0.0)
