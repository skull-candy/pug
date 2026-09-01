from datetime import datetime, timedelta, timezone
import subprocess
import sys

from pug.config import AppConfig, UpdateConfig
from pug.updater import (
    DEFAULT_GITLAB_BASE_URL,
    UpdateManager,
    UpdateSnapshot,
    compare_versions,
    check_branch_update,
    install_update,
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
    assert payload["installed_version"] == "0.2.2"
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
    assert is_newer_version("v1.0b", "0.1.7") is True
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


def _git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True).stdout.strip()


def _repo_with_remote(tmp_path):
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", str(seed)], check=True, capture_output=True)
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test")
    (seed / "src/pug").mkdir(parents=True)
    (seed / "src/pug/updater.py").write_text("def select_channel():\n    pass\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "initial")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "main")
    subprocess.run(["git", "clone", "--branch", "main", str(origin), str(checkout)], check=True, capture_output=True)
    return origin, seed, checkout


def test_branch_check_compares_remote_commit_and_detects_switcher(tmp_path) -> None:
    _origin, seed, checkout = _repo_with_remote(tmp_path)

    current = check_branch_update(checkout, "main")
    assert current["current_commit"] == current["target_commit"]
    assert current["branch_compatible"] is True

    (seed / "feature.txt").write_text("new", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "new feature")
    _git(seed, "push", "origin", "main")

    available = check_branch_update(checkout, "main")
    assert available["current_commit"] != available["target_commit"]


def test_release_install_switches_to_exact_tag(tmp_path, monkeypatch) -> None:
    _origin, seed, checkout = _repo_with_remote(tmp_path)
    _git(seed, "tag", "v2.0.0")
    _git(seed, "push", "origin", "v2.0.0")
    original_run = __import__("pug.updater", fromlist=["run_command"]).run_command

    def skip_pip(command, repo_path, check=True):
        if command[:3] == [sys.executable, "-m", "pip"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        return original_run(command, repo_path, check)

    monkeypatch.setattr("pug.updater.run_command", skip_pip)
    output = []
    install_update(checkout, output.append, channel="release", target="v2.0.0")

    assert _git(checkout, "rev-parse", "HEAD") == _git(checkout, "rev-list", "-n", "1", "v2.0.0")
    assert subprocess.run(["git", "-C", str(checkout), "symbolic-ref", "-q", "HEAD"]).returncode != 0
    assert any("exact release tag v2.0.0" in line for line in output)


def test_branch_install_switches_to_compatible_feature_branch(tmp_path, monkeypatch) -> None:
    _origin, seed, checkout = _repo_with_remote(tmp_path)
    _git(seed, "switch", "-c", "feature/pve")
    (seed / "pve.txt").write_text("enabled", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "pve feature")
    _git(seed, "push", "-u", "origin", "feature/pve")
    original_run = __import__("pug.updater", fromlist=["run_command"]).run_command

    def skip_pip(command, repo_path, check=True):
        if command[:3] == [sys.executable, "-m", "pip"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        return original_run(command, repo_path, check)

    monkeypatch.setattr("pug.updater.run_command", skip_pip)
    install_update(checkout, lambda _line: None, channel="branch", target="feature/pve")

    assert _git(checkout, "branch", "--show-current") == "feature/pve"
    assert (checkout / "pve.txt").read_text(encoding="utf-8") == "enabled"


def test_update_check_failure_is_visible(monkeypatch) -> None:
    def fail(_config):
        raise OSError("network unavailable")

    monkeypatch.setattr("pug.updater.check_for_update", fail)
    snapshot = UpdateManager(config=AppConfig()).check()

    assert snapshot.status == "failed"
    assert snapshot.error == "network unavailable"
