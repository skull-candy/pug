import sys
import time

from pug.config import DiagnosticsConfig
from pug.diagnostics import DiagnosticManager, diagnostic_command


def test_diagnostic_command_maps_actions_to_config() -> None:
    config = DiagnosticsConfig(
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
    config = DiagnosticsConfig(self_test_command=command, self_test_selection="2", command_timeout_seconds=10)

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
