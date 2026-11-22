"""Section "Gmina i trafność metody": SMSR for the commune next to the parcel's result, and how often the
method agreed with SMSR, each measure beside the score of the answer "always the more frequent one".

One SMSR object feeds the row under the verdict and this section (`ctx.smsr`); the scores come from
metrics.json through `ctx.agreement`. The section states "not loaded" only when that object is empty.
"""

from __future__ import annotations

from app.charts.calibration import calibration_svg
from app.context import ReportContext
from app.fmt import dec
from app.models import SOIL_CATEGORIES, Agreement, ConfusionTable, KeyValue, Section, SmsrRow, TextPart
from app.sections import placeholder
from app.smsr import symbol_words
from app.smsr.pages import PageUnavailable, load_page
from app.smsr.parser import SmsrPageError, parse_commune_page
from app.validation.agreement import scores

TARGET_GMINA_YEARS = 300
HEADING = "Gmina i trafność metody"
MAJORITY = "zawsze częstsza odpowiedź"

SYMBOL_SHORT = {
    "+": "susza",
    "-": "brak suszy",
    "x": "bez oceny",
    "#": "uprawa niewskazana",
    "*": "brak takich gleb",
    "n": "bez oceny",
}

EXPLAIN = {
    "CSI": "Trafienia podzielone przez wszystkie przypadki, w których susza wystąpiła albo została zapowiedziana; trafne „brak” nie liczą się.",
    "POD": "Jaka część susz ocenionych przez SMSR została przez metodę wykryta.",
    "FAR": "Jaka część zapowiedzi suszy nie potwierdziła się w SMSR.",
    "Peirce": "Wykryte susze minus fałszywe alarmy wśród przypadków bez suszy; 0 znaczy tyle co rzut monetą, 1 to bezbłędna metoda.",
}


def _pending(ctx: ReportContext) -> Section:
    """The measurement has fewer than 300 commune-years: one sentence, no table."""
    n = ctx.metrics.get("smsr.n_gmina_years") or 0
    sentence = f"Pomiar zgodności: w toku, {n} z {TARGET_GMINA_YEARS} gmino-lat."
    section = placeholder("gmina", HEADING, sentence)
    section.reason = sentence
    section.summary = [TextPart(text=sentence)]
    if ctx.agreement is not None:
        ctx.agreement.sentence = sentence
    return section


def _smsr_ok(smsr: SmsrRow | None) -> bool:
    return smsr is not None and smsr.state == "ok" and smsr.symbol is not None


def _category_symbols(ctx: ReportContext) -> dict[str, str]:
    """Symbol of the parcel's period and crop for every soil category, from the commune's SMSR page."""
    smsr = ctx.smsr
    assert smsr is not None and smsr.year and smsr.period_n
    own = {smsr.soil_category: smsr.symbol} if smsr.soil_category and smsr.symbol else {}
    try:
        page = load_page(smsr.year, ctx.parcel.teryt_commune)
        table = parse_commune_page(page.html)
    except (PageUnavailable, SmsrPageError):
        return {k: v for k, v in own.items() if k}
    out = {}
    for cat in SOIL_CATEGORIES:
        symbol = table.symbol(smsr.crop_label, cat, smsr.period_n)
        if symbol:
            out[cat] = symbol
    return out or {k: v for k, v in own.items() if k}


def _difference(ctx: ReportContext, smsr: SmsrRow, k: int | None) -> str:
    """One sentence on why our result and the commune's can differ."""
    v = ctx.verdict
    ours_below = v is not None and v.state == "below"
    theirs = smsr.symbol
    if v is None or v.state not in ("below", "above"):
        return "Wynik dla działki dotyczy jednej działki, a SMSR całej gminy na danej kategorii gleby, więc mogą się różnić."
    if theirs == "+" and ours_below or theirs == "-" and not ours_below:
        return "Wynik działki i wynik gminy są zgodne."
    if theirs == "-":
        cause = (
            "SMSR ocenia całą gminę dla kategorii gleby, a bilans liczony jest z pogody dla punktu działki"
        )
    elif theirs == "+":
        cause = (
            "SMSR uśrednia stan gleby i roślin w gminie, a bilans opiera się na opadzie i parowaniu działki"
        )
    else:
        return "SMSR nie ocenia tej komórki tabeli, więc nie ma z czym porównać wyniku działki."
    near = (
        f" Blisko progu ({dec(abs(v.margin_mm), 0)} mm) metoda zgadzała się z SMSR rzadziej."
        if v.margin_mm is not None and abs(v.margin_mm) < 25
        else ""
    )
    return f"Wynik działki i gminy różnią się, bo {cause}.{near}"


def _always_drought(a: Agreement) -> dict[str, float | None]:
    t = a.table
    if t is None:
        return {}
    return scores(
        ConfusionTable(
            hits=t.hits + t.misses,
            false_alarms=t.false_alarms + t.correct_negatives,
            misses=0,
            correct_negatives=0,
        )
    )


def _advisor(a: Agreement) -> list[KeyValue]:
    always = _always_drought(a)
    clim = a.baselines.get("klimatologia gminy")
    always_csi = a.baselines.get("zawsze susza")

    def vs(value: float | None, ref_always: float | None, ref_clim: float | None = None) -> str:
        parts = [
            f"metoda {dec(value, 2)}",
            f"zawsze susza {dec(ref_always, 2)}" if ref_always is not None else "",
        ]
        if ref_clim is not None:
            parts.append(f"klimatologia gminy {dec(ref_clim, 2)}")
        return " · ".join(p for p in parts if p)

    return [
        KeyValue(key="CSI", value=f"{vs(a.csi, always_csi, clim)}. {EXPLAIN['CSI']}"),
        KeyValue(key="POD", value=f"{vs(a.pod, always.get('pod'))}. {EXPLAIN['POD']}"),
        KeyValue(key="FAR", value=f"{vs(a.far, always.get('far'))}. {EXPLAIN['FAR']}"),
        KeyValue(key="Peirce", value=f"{vs(a.peirce, always.get('peirce'))}. {EXPLAIN['Peirce']}"),
    ]


def _by_year(ctx: ReportContext) -> list[KeyValue]:
    """One row per year 2020-2026: CSI with its 95% interval and the number of "+" symbols, from metrics.json."""
    rows = []
    for year in range(2020, 2027):
        base = f"smsr.by_year.{year}"
        csi = ctx.metrics.get(f"{base}.csi")
        if csi is None:
            continue
        lo, hi = ctx.metrics.get(f"{base}.csi_ci_low"), ctx.metrics.get(f"{base}.csi_ci_high")
        interval = f" (przedział 95%: {dec(lo, 2)}–{dec(hi, 2)})" if lo is not None and hi is not None else ""
        plus = ctx.metrics.get(f"{base}.plus_count")
        count = f"{dec(plus)}" if plus is not None else "brak"
        rows.append(KeyValue(key=str(year), value=f"CSI {dec(csi, 2)}{interval}|{count}"))
    return rows


def frame_sentence(a: Agreement) -> str:
    """The frame under "Cały raport w skrócie": the method's score and the trivial answer's, per 100 cases."""
    if not a.available or a.k_per_100 is None or a.accuracy_majority is None:
        return a.sentence
    t = round(100 * a.accuracy_majority + 1e-9)
    text = a.sentence.replace("przypadków.", f"przypadków; odpowiedź „{MAJORITY}” w {t} na 100.", 1)
    return text


def build(ctx: ReportContext) -> Section:
    a = ctx.agreement
    if a is None or not a.available or a.table is None or (a.n_gmina_years or 0) < TARGET_GMINA_YEARS:
        return _pending(ctx)
    a.sentence = frame_sentence(a)
    smsr = ctx.smsr
    sentences: list[str] = []
    how = ""
    if _smsr_ok(smsr):
        assert smsr is not None
        cats = _category_symbols(ctx)
        ours = (
            f"bilans: {ctx.verdict.badge.lower()}"
            if ctx.verdict and ctx.verdict.badge
            else "bilans: brak oceny"
        )
        by_cat = ", ".join(f"kat. {c}: {SYMBOL_SHORT.get(s, 'bez oceny')}" for c, s in cats.items())
        sentences.append(
            f"SMSR dla gminy {smsr.commune}, okres {smsr.period_n}: {symbol_words(smsr.symbol or '', smsr.area_share_pct)} "
            f"(gleba działki: kat. {smsr.soil_category}); {ours}."
        )
        if by_cat:
            sentences.append(f"Wynik SMSR dla każdej kategorii gleby: {by_cat}.")
        sentences.append(_difference(ctx, smsr, a.k_per_100))
        how = f"Ocena SMSR IUNG-PIB dla gminy {smsr.commune}, tabela z {smsr.year} r."
    else:
        reason = (
            smsr.reason
            if smsr and smsr.reason
            else f"Brak: oceny SMSR dla gminy {ctx.parcel.commune}, bo tabeli tej gminy nie ma."
        )
        sentences.append(reason)
    section = placeholder("gmina", HEADING, "x")  # for number and title
    section.state = "ready"
    section.reason = ""
    section.summary = [TextPart(text=a.sentence)]
    section.sentences = sentences
    section.how = (
        how or "Zgodność zmierzono na gminach testowych, które metoda widziała dopiero po dostrojeniu."
    )
    section.advisor = _advisor(a)
    section.advisor += _by_year(ctx)
    margin = ctx.verdict.margin_mm if ctx.verdict else None
    section.chart_svg = calibration_svg(
        ctx.metrics, margin, "Krzywa kalibracji: odsetek „+” w SMSR według marginesu bilansu od progu"
    )
    return section
