from datetime import datetime, timezone

from pug.updater import PUBLIC_REPO_URL, UpdateManager, UpdateSnapshot


def test_update_snapshot_serializes_for_web_ui() -> None:
    checked = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)
    snapshot = UpdateSnapshot(
        status="available",
        update_available=True,
        current_commit="abc123",
        latest_commit="def456",
        branch="main",
        checked_at=checked,
        output=["checked"],
    )

    payload = snapshot.to_dict()

    assert payload["status"] == "available"
    assert payload["update_available"] is True
    assert payload["checked_at"] == "2026-07-04T12:00:00+00:00"
    assert payload["output"] == ["checked"]


def test_update_manager_defaults_to_public_repo() -> None:
    snapshot = UpdateManager().snapshot()

    assert snapshot.remote == PUBLIC_REPO_URL
