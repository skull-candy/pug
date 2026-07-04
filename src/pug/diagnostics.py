from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pug.config import DiagnosticsConfig


@dataclass(frozen=True)
class DiagnosticSnapshot:
    status: str = "idle"
    action: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    return_code: int | None = None
    output: list[str] = field(default_factory=list)
    error: str = ""


class DiagnosticManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = DiagnosticSnapshot()

    def snapshot(self) -> DiagnosticSnapshot:
        with self._lock:
            return DiagnosticSnapshot(
                status=self._snapshot.status,
                action=self._snapshot.action,
                started_at=self._snapshot.started_at,
                finished_at=self._snapshot.finished_at,
                return_code=self._snapshot.return_code,
                output=list(self._snapshot.output),
                error=self._snapshot.error,
            )

    def start(self, action: str, config: DiagnosticsConfig) -> bool:
        command, input_lines = diagnostic_command(action, config)
        with self._lock:
            if self._snapshot.status == "running":
                return False
            self._snapshot = DiagnosticSnapshot(
                status="running",
                action=action,
                started_at=datetime.now(timezone.utc),
                output=[f"Starting {diagnostic_label(action)} with command: {' '.join(command)}"],
            )
        thread = threading.Thread(
            target=self._run,
            args=(action, command, input_lines, config.command_timeout_seconds),
            name=f"diagnostic-{action}",
            daemon=True,
        )
        thread.start()
        return True

    def _run(self, action: str, command: list[str], input_lines: list[str], timeout_seconds: int) -> None:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            self._finish("failed", action, None, error=str(exc))
            return

        timer = threading.Timer(timeout_seconds, process.kill)
        timer.start()
        try:
            assert process.stdin is not None
            process.stdin.write("".join(f"{line}\n" for line in input_lines))
            process.stdin.close()
            assert process.stdout is not None
            for line in process.stdout:
                self._append_output(line.rstrip("\n"))
            return_code = process.wait()
        finally:
            timer.cancel()

        if return_code == 0:
            self._finish("completed", action, return_code)
        elif return_code < 0:
            self._finish("failed", action, return_code, error="Diagnostic command was terminated.")
        else:
            self._finish("failed", action, return_code)

    def _append_output(self, line: str) -> None:
        with self._lock:
            output = [*self._snapshot.output, line]
            self._snapshot = DiagnosticSnapshot(
                status=self._snapshot.status,
                action=self._snapshot.action,
                started_at=self._snapshot.started_at,
                finished_at=self._snapshot.finished_at,
                return_code=self._snapshot.return_code,
                output=output[-400:],
                error=self._snapshot.error,
            )

    def _finish(self, status: str, action: str, return_code: int | None, error: str = "") -> None:
        with self._lock:
            self._snapshot = DiagnosticSnapshot(
                status=status,
                action=action,
                started_at=self._snapshot.started_at,
                finished_at=datetime.now(timezone.utc),
                return_code=return_code,
                output=list(self._snapshot.output),
                error=error,
            )


def diagnostic_command(action: str, config: DiagnosticsConfig) -> tuple[list[str], list[str]]:
    if action == "self_test":
        return list(config.self_test_command), [config.self_test_selection, "Q"]
    if action == "battery_calibration":
        return list(config.battery_calibration_command), [config.battery_calibration_selection]
    raise ValueError(f"unsupported diagnostic action: {action}")


def diagnostic_label(action: str) -> str:
    return {
        "self_test": "self test",
        "battery_calibration": "battery calibration",
    }.get(action, action.replace("_", " "))
