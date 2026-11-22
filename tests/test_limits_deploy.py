"""The deploy scripts carry the limits: one worker, MemoryMax and TasksMax, also for an installed server."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_unit_has_limits() -> None:
    text = (ROOT / "deploy/bootstrap.sh").read_text(encoding="utf-8")
    assert "--workers 1" in text and "--workers 2" not in text
    assert "MemoryMax=2800M" in text and "TasksMax=600" in text


def test_deploy_updates_installed_unit() -> None:
    text = (ROOT / "deploy/deploy.sh").read_text(encoding="utf-8")
    assert "MemoryMax=2800M" in text and "TasksMax=600" in text and "--workers 1" in text
    assert "daemon-reload" in text
