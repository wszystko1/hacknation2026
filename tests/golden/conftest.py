"""Golden locations: the option that points the tests at a running application.

Without `--base-url` (or the GOLDEN_BASE_URL variable) the tests run offline on the frozen data of
demo/data/locations/ with the TestClient. With it, every report is fetched over HTTP from the running application.
The option is registered here, so it is available for `pytest tests/golden --base-url https://ADDRESS`;
the plain `pytest` run of the whole suite does not need it (the tests read it with a default).
"""

from __future__ import annotations

import os


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--base-url",
        action="store",
        default=os.environ.get("GOLDEN_BASE_URL") or None,
        help="address of the running application (e.g. https://1-2-3-4.sslip.io); empty: offline, frozen data",
    )
    parser.addoption(
        "--golden-only",
        action="store",
        default=None,
        help="run only the location with this id (e.g. dobrcz)",
    )


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "golden: golden locations (hand-picked parcels with expert expectations)")


def pytest_collection_modifyitems(config, items) -> None:
    """The golden suite is opt-in for the gate (it is a quality report, not a regression gate): GOLDEN=1, --base-url or -m golden."""
    import pytest

    if config.getoption("--base-url") or os.environ.get("GOLDEN") == "1" or "golden" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="złote lokalizacje: uruchamiane przez scripts/golden_check.sh (GOLDEN=1 albo --base-url)")
    for item in items:
        if "tests/golden" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip)
