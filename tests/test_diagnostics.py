import sys
import time

from pug.config import DiagnosticsConfig
from pug.diagnostics import DiagnosticManager, diagnostic_command


def test_diagnostic_command_maps_actions_to_config() -> None:
    config = DiagnosticsConfig(
        before_command=[],
        after_command=[],
        self_test_command=["self"],
        self_test_selection="2",
        battery_calibration_command=["calibrate"],
        battery_calibration_selection="10",
    )

    assert diagnostic_command("self_test", config) == (["self"], ["2", "Q"])
    assert diagnostic_command("battery_calibration", config) == (["calibrate"], ["10"])


def test_diagnostic_manager_runs_command_and_records_result() -> None:
    manager = DiagnosticManager()
    command = [
        sys.executable,
        "-c",
        "import sys; data=sys.stdin.read(); print('input=' + data.replace('\\n', '|'))",
    ]
    config = DiagnosticsConfig(before_command=[], after_command=[], self_test_command=command, self_test_selection="2", command_timeout_seconds=10)

    assert manager.start("self_test", config) is True
    for _ in range(50):
        snapshot = manager.snapshot()
        if snapshot.status != "running":
            break
        time.sleep(0.05)

    snapshot = manager.snapshot()
    assert snapshot.status == "completed"
    assert snapshot.return_code == 0
    assert any("input=2|Q|" in line for line in snapshot.output)


def test_diagnostic_manager_can_abort_battery_calibration_and_restore() -> None:
    manager = DiagnosticManager()
    command = [
        sys.executable,
        "-c",
        (
            "import sys; "
            "print('ready', flush=True); "
            "selection=sys.stdin.readline(); "
            "print('selected=' + selection.strip(), flush=True); "
            "abort=sys.stdin.readline(); "
            "print('abort=' + repr(abort), flush=True)"
        ),
    ]
    restore_command = [sys.executable, "-c", "print('restored')"]
    config = DiagnosticsConfig(
        before_command=[],
        after_command=restore_command,
        battery_calibration_command=command,
        battery_calibration_selection="10",
        command_timeout_seconds=10,
    )

    assert manager.start("battery_calibration", config) is True
    for _ in range(50):
        if any("selected=10" in line for line in manager.snapshot().output):
            break
        time.sleep(0.05)

    assert manager.abort() is True
    for _ in range(50):
        snapshot = manager.snapshot()
        if snapshot.status != "running":
            break
        time.sleep(0.05)

    snapshot = manager.snapshot()
    assert snapshot.status == "aborted"
    assert any("Sent ENTER" in line for line in snapshot.output)
    assert any("restored" in line for line in snapshot.output)
