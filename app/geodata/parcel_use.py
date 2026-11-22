"""Land use of a parcel (EGiB "użytek"): is it farmland at all? Forest, built-up land and roads are not.

The EGiB WFS answer for a parcel may carry the land-use class (OZU/OFU codes such as R, Ł, Ps, Lś, B, dr).
When the service gives none, the answer is None ("unknown"), never a guess.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import parcel_wfs
from .errors import GeodataError

log = logging.getLogger(__name__)

PROPERTY_KEYS = ("OZU", "OFU", "OZNACZENIE_UZYTKU", "UZYTEK", "KLASOUZYTEK")
_FOREST = {"Ls", "Lz", "Lzr", "LS", "LZ"}
_BUILT = {"B", "Ba", "Bi", "Bp", "Bz", "K", "Tk", "Ti", "Tp", "Tr", "Ws", "Wm", "Wp", "Wsr", "Wz"}
_ROAD = {"dr", "Tk", "Ti", "Tp", "Dr"}
_WATER = {"Ws", "Wm", "Wp", "Wsr", "Wz"}
_FARM = {"R", "Ł", "Ps", "Lr", "S", "Br", "Wsr", "W", "N"}


@dataclass(frozen=True)
class LandUse:
    code: str
    kind: str  # "forest" | "built" | "road" | "water" | "farm" | "other"

    @property
    def farmland(self) -> bool:
        return self.kind == "farm"

    @property
    def label(self) -> str:
        return {"forest": "las", "built": "zabudowa", "road": "droga", "water": "wody"}.get(self.kind, "inny")


def classify(code: str) -> LandUse:
    """Class of the first letters of an EGiB land-use code ("R", "Lzr", "Bi", "dr", "Ps IV")."""
    token = (code or "").strip().split()[0] if (code or "").strip() else ""
    root = token.split("-")[0]
    if root in _FOREST or root.startswith("Ls") or root.startswith("Lz"):
        kind = "forest"
    elif root in _ROAD:
        kind = "road"
    elif root in _WATER:
        kind = "water"
    elif root in _BUILT or root.startswith("B"):
        kind = "built"
    elif root in _FARM or root.startswith(("R", "Ł", "Ps", "Lr", "Br")):
        kind = "farm"
    else:
        kind = "other"
    return LandUse(root, kind)


def land_use_from_properties(props: dict) -> LandUse | None:
    for key in PROPERTY_KEYS:
        value = props.get(key)
        if value:
            return classify(str(value))
    return None


def fetch_land_use(parcel_id: str, *, deadline: float | None = None) -> LandUse | None:
    """Land use from the EGiB WFS; None when the service is silent or has no such field."""
    flt = f"<Filter {parcel_wfs._FILTER_NS}>{parcel_wfs._equal('ID_DZIALKI', parcel_id)}</Filter>"
    try:
        for feature in parcel_wfs._query({"FILTER": flt}, deadline):
            props = feature.get("properties") or {}
            if str(props.get("ID_DZIALKI")) == parcel_id:
                return land_use_from_properties(props)
    except GeodataError:
        log.info("land use of %s unavailable", parcel_id)
    return None


def not_farmland_sentence(use: LandUse) -> str:
    return (
        f"Brak: oceny nawadniania, bo działka nie jest użytkiem rolnym ({use.label}, użytek {use.code}); "
        "ocena suszy rolniczej nie ma zastosowania."
    )
