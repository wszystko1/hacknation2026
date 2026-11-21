"""Golden-path demo as Playwright scenes (sync API).

`make demo` starts the app and runs SCENES in order in headless Chrome; each scene gets a Playwright `page`
and the base URL. Titles are Polish and fixed. Each scene ends on the screen its title names and asserts
the value a viewer should see. The scene bodies live in demo/steps/.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo.steps import (  # noqa: E402
    advisor_pdf,
    agreement,
    out_of_season,
    parcel_photo,
    plan,
    retention,
    sources,
    summary,
    verdict,
)

SCENES = [
    ("Działka z ewidencji na zdjęciu", parcel_photo.scene),
    ("Werdykt: bilans wobec progu z rozporządzenia", verdict.scene),
    ("Cały raport w skrócie", summary.scene),
    ("Gdzie zatrzymać wodę na działce", retention.scene),
    ("Plan działań: przełącznik „W planie”", plan.scene),
    ("Zgodność z oceną państwa (SMSR)", agreement.scene),
    ("Źródła, czasy i braki danych", sources.scene),
    ("Widok doradcy i raport PDF", advisor_pdf.scene),
    ("Raport na dziś: poza okresem monitoringu suszy", out_of_season.scene),
]
