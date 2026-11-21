"""Shared data models of the parcel water report (the contract between modules, the UI and the JSON API).

Every module fills one part of `Report`; templates and `/api/raport` read the same objects.
Changes to this file are contract changes: see contracts/README.md.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- vocabulary of the drought regulation


class CropGroup(StrEnum):
    """The 14 crop groups of Dz.U. 2019 poz. 739 (names as in SMSR IUNG tables) plus "Inna uprawa".

    The value is the URL code (`uprawa=zboza_jare`); `CROP_LABELS` gives the Polish name.
    """

    BURAK_CUKROWY = "burak_cukrowy"
    CHMIEL = "chmiel"
    DRZEWA_OWOCOWE = "drzewa_owocowe"
    KRZEWY_OWOCOWE = "krzewy_owocowe"
    KUKURYDZA_KISZONKA = "kukurydza_kiszonka"
    KUKURYDZA_ZIARNO = "kukurydza_ziarno"
    ROSLINY_STRACZKOWE = "rosliny_straczkowe"
    RZEPAK = "rzepak"
    TRUSKAWKI = "truskawki"
    TYTON = "tyton"
    WARZYWA = "warzywa"
    ZBOZA_JARE = "zboza_jare"
    ZBOZA_OZIME = "zboza_ozime"
    ZIEMNIAK = "ziemniak"
    INNA = "inna"


CROP_LABELS: dict[CropGroup, str] = {
    CropGroup.BURAK_CUKROWY: "Burak cukrowy",
    CropGroup.CHMIEL: "Chmiel",
    CropGroup.DRZEWA_OWOCOWE: "Drzewa owocowe",
    CropGroup.KRZEWY_OWOCOWE: "Krzewy owocowe",
    CropGroup.KUKURYDZA_KISZONKA: "Kukurydza na kiszonkę",
    CropGroup.KUKURYDZA_ZIARNO: "Kukurydza na ziarno",
    CropGroup.ROSLINY_STRACZKOWE: "Rośliny strączkowe",
    CropGroup.RZEPAK: "Rzepak i rzepik",
    CropGroup.TRUSKAWKI: "Truskawki",
    CropGroup.TYTON: "Tytoń",
    CropGroup.WARZYWA: "Warzywa gruntowe",
    CropGroup.ZBOZA_JARE: "Zboża jare",
    CropGroup.ZBOZA_OZIME: "Zboża ozime",
    CropGroup.ZIEMNIAK: "Ziemniak",
    CropGroup.INNA: "Inna uprawa",
}

# Order of the crop list in the form: alphabetical (Polish), "Inna uprawa" last.
CROP_CHOICES: list[CropGroup] = list(CROP_LABELS)

SoilCategory = Literal["I", "II", "III", "IV"]
SOIL_CATEGORIES: tuple[SoilCategory, ...] = ("I", "II", "III", "IV")

# Fixed texts the jury and the scenes check word for word.
BADGE_BELOW = "Bilans poniżej progu suszy (szacunek dla działki)"
BADGE_ABOVE = "Bilans powyżej progu suszy (szacunek dla działki)"
DISCLAIMER = "To nie jest urzędowe stwierdzenie suszy; we wniosku liczy się ocena SMSR IUNG dla gminy"
OUT_OF_SEASON = "Poza okresem monitoringu suszy (21.III–30.IX)"
LAW_THRESHOLDS = "Dz.U. 2019 poz. 739"
LAW_WATER = "Prawo wodne, Dz.U. 2026 poz. 1335"

View = Literal["rolnik", "doradca"]

# ---------------------------------------------------------------- request


class ReportRequest(BaseModel):
    """What the user asked for. Built from the query string of /raport and /api/raport."""

    parcel_id: str = Field(description="full TERYT parcel id, e.g. 040303_2.0002.189/13")
    day: date = Field(description="analysis date")
    crop: CropGroup
    view: View = "rolnik"
    plan: list[int] = Field(default_factory=list, description="numbers of actions switched to 'W planie'")
    soil_override: SoilCategory | None = Field(default=None, description="soil category set by the advisor")


class FieldError(BaseModel):
    """An input error shown next to its field (field names as in the query string)."""

    field: Literal["dzialka", "data", "uprawa", "gleba"]
    message: str


# ---------------------------------------------------------------- parcel and map


class ParcelInfo(BaseModel):
    id: str
    number: str  # "189/13"
    precinct: str  # obręb
    commune: str  # gmina
    county: str
    voivodeship: str
    teryt_commune: str  # 7 characters, e.g. "0403032" (SMSR uses it)
    area_ha: float
    centroid_lonlat: tuple[float, float]


class MapMarker(BaseModel):
    """A numbered action on the photo (same number as the action in the report)."""

    n: int
    x: float  # image pixel column
    y: float  # image pixel row
    kind: str


class MapView(BaseModel):
    """Orthophoto with the SVG overlay, in the image's pixel space."""

    image_url: str
    width: int
    height: int
    m_per_px: float
    outline_px: list[list[tuple[float, float]]]  # rings, first = outline
    outlet_px: tuple[float, float] | None = None  # lowest point of the outline
    ditches_px: list[list[tuple[float, float]]] = Field(default_factory=list)
    flow_px: list[list[tuple[float, float]]] = Field(default_factory=list)  # polylines, arrow at the end
    markers: list[MapMarker] = Field(default_factory=list)
    label: str  # "189/13 · 21,53 ha"
    attribution: str = "ortofotomapa i obrys: GUGiK"


class SourceRow(BaseModel):
    """One row of "Skąd są dane" and of the sources table."""

    key: str  # parcel, weather, ortho, soil, satellite, terrain, water, smsr, forecast, ...
    label: str  # "Obrys działki"
    provider: str  # "ULDK GUGiK"
    gave: str = ""  # what it gave for this parcel ("21,53 ha", "opad i parowanie 2015–2023")
    status: Literal["ok", "fallback", "missing", "waiting", "copy"]
    elapsed_s: float | None = None
    retrieved_at: str = ""  # ISO time of the original download
    resolution: str = ""
    reason: str = ""  # why missing or fallback, in Polish
    url: str = ""


# ---------------------------------------------------------------- assessment


class SoilInfo(BaseModel):
    category: SoilCategory | None
    source: Literal["iung", "soilgrids", "doradca", "brak"]
    words: str  # "gleba bardzo podatna na suszę (kat. I)"
    neighbour_category: SoilCategory | None = None  # texture near a class boundary
    sand_pct: float | None = None
    silt_pct: float | None = None
    clay_pct: float | None = None
    note: str = ""


class PeriodBalance(BaseModel):
    """Climatic water balance (KBW) in one of the 14 periods of the regulation."""

    n: int = Field(ge=1, le=14)
    start: date
    end: date
    precip_mm: float
    et0_mm: float
    kbw_mm: float  # precip - et0
    threshold_mm: float | None  # None: the table gives no threshold here ("-", "x", "Inna uprawa")
    margin_mm: float | None  # kbw - threshold; negative = below the threshold
    complete: bool  # the period ended on or before the analysis date
    days: int  # days with data in the window (60 when complete)


VerdictState = Literal["below", "above", "running", "out_of_season", "no_threshold", "no_data"]


class Verdict(BaseModel):
    state: VerdictState
    badge: str  # BADGE_BELOW / BADGE_ABOVE / "Sezon 2026" / "" when no badge
    kbw_mm: float | None
    threshold_mm: float | None
    margin_mm: float | None
    period: PeriodBalance | None  # the period on top: smallest margin, or the running one
    periods: list[PeriodBalance] = Field(default_factory=list)
    sentence: (
        str  # "W tych 60 dniach wyparowało o 219 mm więcej wody, niż spadło. To 33 mm poniżej progu ..."
    )
    how: str  # "opad 61 − parowanie 280 = −219 mm (okres 7, 21.05–20.07.2023) · próg z Dz.U. 2019 poz. 739"
    disclaimer: str = DISCLAIMER
    season_year: int | None = None  # out_of_season: the season shown
    note: str = ""  # "okres jeszcze trwa: 34 z 60 dni"


class SmsrRow(BaseModel):
    """The state's assessment (SMSR IUNG) for the commune, period, crop and the parcel's soil category."""

    state: Literal["ok", "missing", "before_2020", "waiting"]
    commune: str
    year: int | None = None
    period_n: int | None = None
    crop_label: str = ""
    soil_category: SoilCategory | None = None
    symbol: str | None = None  # "+", "-", "x", "#", "*", "n"
    words: str = ""  # "susza", "brak suszy", ...
    area_share_pct: float | None = None  # share of the commune's area at risk
    url: str = ""
    reason: str = ""


class CropCondition(BaseModel):
    """Plants on the parcel from Sentinel-2 (NDMI vs the median of the same dekad in earlier seasons)."""

    state: Literal["ok", "missing", "waiting"]
    words: str  # farmer view: "rośliny suchsze niż zwykle w tej dekadzie"
    scene_date: date | None = None
    ndvi: float | None = None
    ndmi: float | None = None
    ndmi_median: float | None = None
    n_seasons: int = 0
    reason: str = ""


# ---------------------------------------------------------------- recommendations

CauseCode = Literal["malo_opadu", "duze_parowanie", "gleba_lekka", "splyw", "faza_wrazliwa"]


class Cause(BaseModel):
    """A diagnosed cause of the water deficit; every action answers one of them."""

    code: CauseCode
    words: str  # "spadło 61 mm, o 71 mm mniej niż zwykle"
    strength_mm: float | None = None  # contribution to the deficit, when measurable


class Diagnosis(BaseModel):
    """Every cause whose rule holds, strongest first. Empty when there is no assessment (then no recommendations)."""

    causes: list[Cause] = Field(default_factory=list)
    usual_kbw_mm: float | None = None  # median balance of the same period in earlier seasons


Formality = Literal[
    "nic nie trzeba",
    "powiadomienie Wód Polskich",
    "zgłoszenie",
    "pozwolenie wodnoprawne",
    "sprawdź w Wodach Polskich",
]


class LegalNote(BaseModel):
    """The formality under the Water Law for one action (from app/advice/prawo_wodne.csv)."""

    formality: Formality
    article: str = ""  # "art. 394 ust. 1 pkt 9"; empty for "sprawdź w Wodach Polskich"
    quote: str = ""
    pdf_page: int | None = None
    checked_on: date | None = None
    act: str = LAW_WATER
    extra: list[str] = Field(default_factory=list)  # art. 234 ust. 1, consent of the neighbour, ...


class Place(BaseModel):
    """Where on the parcel an action goes, computed from its geometry."""

    kind: str  # "punkt wypływu", "rów zadarniony", "pas konturowy", "pas trawy", "zastawka", "niecka", "rów", "zbiornik"
    x_2180: float
    y_2180: float
    lon: float
    lat: float
    px: tuple[float, float] | None = None  # position on the orthophoto
    description: str = ""  # "narożnik płd.-zach., przy granicy"
    catchment_ha: float | None = None  # catchment intercepted here, from the runoff analysis (margin ~300 m)


ActionGroup = Literal["retencja", "uprawa", "nawadnianie"]


class Action(BaseModel):
    id: str  # stable code from the action catalogue, e.g. "niecka-przy-wyplywie"
    n: int  # number on the map and in the plan (1..M, unique within a report)
    group: ActionGroup
    title: str
    sentence: str  # with this parcel's numbers
    cause: str  # the diagnosed cause it answers first (one of `causes`)
    causes: list[str] = Field(default_factory=list)  # Cause.words of every diagnosed cause it answers
    effect: str = ""  # literature range from a catalogue row with source and quote, "… (literatura)"; else ""
    when: str  # "po żniwach, do 15.09.2023"
    due: date | None = None  # deadline that places the action on the plan's timeline
    source: str  # "katalog NWRM N01 · CDR 2025"
    legal: LegalNote | None = None
    place: Place | None = None
    no_place_reason: str = ""  # "brak miejsca na działce, bo teren płaski (spadek 0,3%)"
    in_plan: bool = False


# ---------------------------------------------------------------- method quality and forecast


class ConfusionTable(BaseModel):
    hits: int  # we say below, SMSR says drought
    false_alarms: int
    misses: int
    correct_negatives: int


class Agreement(BaseModel):
    """Agreement of the method with SMSR, read from metrics.json (never computed in a request)."""

    available: bool
    sentence: str  # "przy takiej odległości od progu metoda zgadzała się z SMSR w 87 na 100 przypadków"
    k_per_100: int | None = None
    distance_bucket: str = ""  # "0–10 mm", "10–25 mm", "25–50 mm", ">50 mm"
    csi: float | None = None
    pod: float | None = None
    far: float | None = None
    peirce: float | None = None
    base_rate: float | None = None
    csi_gain_vs_baseline: float | None = None
    n_gmina_years: int | None = None
    n_symbols: int | None = None
    table: ConfusionTable | None = None
    baselines: dict[str, float] = Field(default_factory=dict)  # name -> CSI
    # measures for the farmer, each read next to accuracy_majority ("zawsze częstsza odpowiedź")
    accuracy: float | None = None
    balanced_accuracy: float | None = None
    recall: float | None = None
    precision: float | None = None
    accuracy_majority: float | None = None


class ExceedanceForecast(BaseModel):
    """Chance that the balance falls below the threshold before the end of the critical period."""

    state: Literal["ok", "missing", "period_over", "no_threshold"]
    method: Literal["historical", "analog", "gbdt", ""] = ""
    k: int | None = None
    n: int | None = None
    probability: float | None = None
    sentence: str = ""  # "w 4 z 10 wcześniejszych lat dalsza pogoda doprowadziła do przekroczenia progu"
    skill_sentence: str = ""  # one sentence on accuracy, from metrics.json
    what_happened: str = ""  # past dates: what the archive shows


# ---------------------------------------------------------------- sections of the report


SectionId = Literal["historia", "gmina", "przyczyny", "retencja", "uprawa", "plan", "nawadnianie", "zrodla"]

# Order and numbers of sections 1-8 (the verdict is section 0).
SECTION_ORDER: list[tuple[SectionId, int, str]] = [
    ("historia", 1, "10 sezonów"),
    ("gmina", 2, "Gmina i trafność"),
    ("przyczyny", 3, "Przyczyny"),
    ("retencja", 4, "Zatrzymanie wody"),
    ("uprawa", 5, "Uprawa gleby"),
    ("plan", 6, "Plan i termin"),
    ("nawadnianie", 7, "Nawadnianie"),
    ("zrodla", 8, "Źródła i braki"),
]


class TextPart(BaseModel):
    """A piece of a summary sentence; numbers are bold, a warning is in the danger colour."""

    text: str
    bold: bool = False
    warn: bool = False


class KeyValue(BaseModel):
    key: str
    value: str


class Section(BaseModel):
    id: SectionId
    n: int
    title: str  # short name in "Cały raport w skrócie"
    heading: str  # heading of the section ("Gdzie zatrzymać wodę na działce")
    state: Literal["ready", "loading", "missing"]
    summary: list[TextPart] = Field(default_factory=list)  # one sentence with the key numbers
    chip: str = ""  # "Open-Meteo · 1,0 s"
    chart_svg: str = ""  # server-built SVG markup (app/charts), trusted
    sentences: list[str] = Field(default_factory=list)  # 2-3 sentences under the chart
    how: str = ""  # "Jak to policzono"
    advisor: list[KeyValue] = Field(default_factory=list)  # shown in the "Doradca" view
    actions: list[Action] = Field(default_factory=list)
    waiting_for: str = ""  # loading: "pogoda z 10 lat (IMGW)"
    reason: str = ""  # missing: why


class Report(BaseModel):
    request: ReportRequest
    parcel: ParcelInfo
    data_copy: str | None = None  # "kopia danych z 21.11.2026" when the data come from a frozen copy
    map: MapView | None = None
    soil: SoilInfo
    verdict: Verdict
    smsr: SmsrRow
    crop_condition: CropCondition
    diagnosis: Diagnosis = Field(default_factory=Diagnosis)
    action_1: Action | None = None
    action_1_reason: str = ""  # "brak miejsca na działce, bo …" when there is no action 1
    agreement: Agreement
    forecast: ExceedanceForecast
    sections: list[Section]
    sources: list[SourceRow]
    total_s: float

    @property
    def actions(self) -> list[Action]:
        """All actions of the report in plan order (numbers 1..M)."""
        return sorted((a for s in self.sections for a in s.actions), key=lambda a: a.n)

    @property
    def plan_count(self) -> int:
        return sum(1 for a in self.actions if a.in_plan)

    def section(self, section_id: SectionId) -> Section:
        return next(s for s in self.sections if s.id == section_id)
