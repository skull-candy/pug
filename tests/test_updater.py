from datetime import datetime, timedelta, timezone

from pug.config import AppConfig, UpdateConfig
from pug.updater import (
    DEFAULT_GITLAB_BASE_URL,
    UpdateManager,
    UpdateSnapshot,
    compare_versions,
    is_newer_version,
    latest_release_api_url,
    update_check_due,
)


def test_update_snapshot_serializes_for_web_ui() -> None:
    checked = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
    snapshot = UpdateSnapshot(
        status="available",
        update_available=True,
        latest_version="v1.0.0",
        latest_release_url="https://git.vns.ae/ahsan/pug/-/releases/v1.0.0",
        latest_release_name="PUG v1.0.0",
        checked_at=checked,
        output=["checked"],
    )

    payload = snapshot.to_dict()

    assert payload["status"] == "available"
    assert payload["update_available"] is True
    assert payload["installed_version"] == "0.1.6"
    assert payload["latest_version"] == "v1.0.0"
    assert payload["latest_release_url"] == "https://git.vns.ae/ahsan/pug/-/releases/v1.0.0"
    assert payload["checked_at"] == "2026-07-04T12:00:00+00:00"
    assert payload["output"] == ["checked"]


def test_update_manager_defaults_to_gitlab_releases() -> None:
    snapshot = UpdateManager().snapshot()

    assert snapshot.gitlab_base_url == DEFAULT_GITLAB_BASE_URL
    assert snapshot.project_path == "ahsan/pug"
    assert snapshot.check_interval == "7d"


def test_latest_release_api_url_encodes_project_path() -> None:
    assert (
        latest_release_api_url("https://git.example.com/", "group/subgroup/pug")
        == "https://git.example.com/api/v4/projects/group%2Fsubgroup%2Fpug/releases/permalink/latest"
    )


def test_update_check_interval_can_be_disabled() -> None:
    now = datetime(2026, 7, 5, 12, tzinfo=timezone.utc)

    assert update_check_due(UpdateConfig(check_interval="off"), now) is False
    assert update_check_due(UpdateConfig(check_interval="1d"), now) is True
    assert update_check_due(UpdateConfig(check_interval="1d", last_update_check=(now - timedelta(hours=12)).isoformat()), now) is False
    assert update_check_due(UpdateConfig(check_interval="1d", last_update_check=(now - timedelta(days=1, minutes=1)).isoformat()), now) is True
    assert update_check_due(UpdateConfig(check_interval="7d", last_update_check=(now - timedelta(days=2)).isoformat()), now) is False


def test_version_comparison_supports_beta_and_release_tags() -> None:
    assert is_newer_version("v1.0b", "0.1.6") is True
    assert is_newer_version("v1.0.0-beta.1", "v1.0b") is True
    assert is_newer_version("v1.0.0", "v1.0.0-beta.1") is True
    assert compare_versions("v1.0.0", "1.0.0") == 0


def test_disabled_update_manager_never_checks_gitlab(monkeypatch) -> None:
    called = False

    def fake_check_for_update(_config):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("pug.updater.check_for_update", fake_check_for_update)
    manager = UpdateManager(config=AppConfig(update=UpdateConfig(check_interval="off")))

    assert manager.check_if_due() is False
    assert manager.check().status == "disabled"
    assert called is False


def test_manual_update_check_bypasses_interval_gate(monkeypatch) -> None:
    now = datetime(2026, 7, 5, 12, tzinfo=timezone.utc)
    calls = []

    def fake_check_for_update(_config):
        calls.append("checked")
        return {
            "latest_version": "v9.0.0",
            "latest_release_url": "https://git.vns.ae/ahsan/pug/-/releases/v9.0.0",
            "latest_release_name": "PUG v9.0.0",
        }

    monkeypatch.setattr("pug.updater.check_for_update", fake_check_for_update)
    manager = UpdateManager(config=AppConfig(update=UpdateConfig(last_update_check=now.isoformat())))

    assert manager.check().latest_version == "v9.0.0"
    assert calls == ["checked"]
