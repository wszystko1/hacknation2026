"""Reading and checking the three fields (działka, data, uprawa) and the report options from a query string."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from app.geodata import InvalidParcelId, normalize_parcel_id
from app.models import SOIL_CATEGORIES, CropGroup, FieldError, ReportRequest

FIRST_DAY = date(2016, 1, 1)


def parse_request(
    q: Mapping[str, str], today: date | None = None
) -> tuple[ReportRequest | None, list[FieldError]]:
    today = today or date.today()
    errors: list[FieldError] = []
    raw_id = (q.get("dzialka") or "").strip()
    parcel_id = ""
    if not raw_id:
        errors.append(FieldError(field="dzialka", message="Wpisz numer działki, np. 040303_2.0002.189/13"))
    else:
        try:
            parcel_id = normalize_parcel_id(raw_id)
        except (InvalidParcelId, ValueError):
            errors.append(FieldError(field="dzialka", message="Numer ma postać 040303_2.0002.189/13"))
    day = None
    try:
        day = date.fromisoformat((q.get("data") or "").strip())
    except ValueError:
        errors.append(FieldError(field="data", message="Wpisz datę oceny, np. 20.07.2023"))
    if day is not None and not (FIRST_DAY <= day <= today):
        errors.append(
            FieldError(
                field="data", message=f"Data musi być z ostatnich 10 lat, od 1.01.2016 do {today:%d.%m.%Y}"
            )
        )
    crop = None
    try:
        crop = CropGroup((q.get("uprawa") or "").strip())
    except ValueError:
        errors.append(FieldError(field="uprawa", message="Wybierz uprawę z listy"))
    soil = (q.get("gleba") or "").strip() or None
    if soil is not None and soil not in SOIL_CATEGORIES:
        errors.append(FieldError(field="gleba", message="Kategoria gleby to I, II, III albo IV"))
    if errors:
        return None, errors
    plan = sorted({int(p) for p in (q.get("plan") or "").split(",") if p.strip().isdigit()})
    view = "doradca" if q.get("widok") == "doradca" else "rolnik"
    return ReportRequest(
        parcel_id=parcel_id, day=day, crop=crop, view=view, plan=plan, soil_override=soil
    ), []
