"""What every step of the report gets: the request, the downloaded data and the results of earlier steps."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.geodata import FetchResult
from app.models import (
    Action,
    Agreement,
    CropCondition,
    Diagnosis,
    ExceedanceForecast,
    ParcelInfo,
    ReportRequest,
    SmsrRow,
    SoilInfo,
    SourceRow,
    Verdict,
)

ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = ROOT / "metrics.json"


def load_metrics(path: Path = METRICS_PATH) -> dict[str, Any]:
    """metrics.json as a flat dict ("smsr.csi" -> 0.41). Written only by `make eval`; the app only reads it."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    flat: dict[str, Any] = {}

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                walk(f"{prefix}.{k}" if prefix else k, v)
        else:
            flat[prefix] = value

    walk("", raw)
    return flat


@dataclass
class ReportContext:
    """Filled step by step by app.report.build_report; a step reads only what earlier steps filled."""

    request: ReportRequest
    data: FetchResult
    parcel: ParcelInfo
    data_copy: str | None = None  # "kopia danych z 21.11.2026" for frozen copies
    metrics: dict[str, Any] = field(default_factory=load_metrics)
    soil: SoilInfo | None = None
    verdict: Verdict | None = None
    smsr: SmsrRow | None = None
    crop_condition: CropCondition | None = None
    diagnosis: Diagnosis | None = None
    actions: list[Action] = field(default_factory=list)  # numbered 1..M, plan state applied
    forecast: ExceedanceForecast | None = None
    agreement: Agreement | None = None
    extra_sources: list[SourceRow] = field(default_factory=list)  # sources fetched outside app.geodata (SMSR)
    flow_2180: list[list[tuple[float, float]]] = field(
        default_factory=list
    )  # concentrated flow lines from the runoff analysis, for the map (EPSG:2180)
    outlet_2180: tuple[float, float] | None = None  # main outlet on the boundary (runoff or lowest point)
    outlet_catchment_ha: float | None = None  # catchment draining through that outlet
    runoff_reason: str = ""  # "spadek 0,3% jest za mały, by wskazać linię spływu" instead of arrows
