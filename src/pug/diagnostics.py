from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "finished_at": self.finished_at.isoformat() if self.finished_at else "",
            "return_code": self.return_code,
            "output": list(self.output),
            "error": self.error,
        }


class DiagnosticManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._snapshot = DiagnosticSnapshot()
        self._process: subprocess.Popen[str] | None = None
        self._abort_requested = False

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
            self._abort_requested = False
        thread = threading.Thread(
            target=self._run,
            args=(action, command, input_lines, list(config.before_command), list(config.after_command), config.command_timeout_seconds),
            name=f"diagnostic-{action}",
            daemon=True,
        )
        thread.start()
        return True

    def abort(self) -> bool:
        with self._lock:
            if self._snapshot.status != "running":
                return False
            self._abort_requested = True
        self._append_output("Abort requested from Web UI.")
        with self._process_lock:
            process = self._process
        if process is None:
            return True
        try:
            if process.stdin and not process.stdin.closed:
                process.stdin.write("\n")
                process.stdin.flush()
                self._append_output("Sent ENTER to diagnostic process.")
        except OSError as exc:
            self._append_output(f"Unable to send abort input: {exc}")
        threading.Thread(target=self._force_stop_if_needed, args=(process,), name="diagnostic-abort", daemon=True).start()
        return True

    def _run(
        self,
        action: str,
        command: list[str],
        input_lines: list[str],
        before_command: list[str],
        after_command: list[str],
        timeout_seconds: int,
    ) -> None:
        self._append_output("UPS monitoring is paused while this diagnostic owns the UPS connection.")
        if before_command:
            before_result = self._run_simple_command("Preparing UPS diagnostic", before_command, timeout_seconds=60)
            if before_result != 0:
                self._finish("failed", action, before_result, error="Diagnostic preparation command failed.")
                return

        return_code: int | None = None
        error = ""
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
            return_code = None
            error = str(exc)
        else:
            timer = threading.Timer(timeout_seconds, process.kill)
            timer.start()
            with self._process_lock:
                self._process = process
            try:
                assert process.stdin is not None
                process.stdin.write("".join(f"{line}\n" for line in input_lines))
                process.stdin.flush()
                if action != "battery_calibration":
                    process.stdin.close()
                assert process.stdout is not None
                for line in process.stdout:
                    self._append_output(line.rstrip("\n"))
                return_code = process.wait()
            finally:
                timer.cancel()
                with self._process_lock:
                    if self._process is process:
                        self._process = None
                try:
                    if process.stdin and not process.stdin.closed:
                        process.stdin.close()
                except OSError:
                    pass

        after_result = 0
        if after_command:
            after_result = self._run_simple_command("Restoring UPS monitoring", after_command, timeout_seconds=60)

        if error:
            self._finish("failed", action, return_code, error=error)
            return

        if after_result != 0:
            self._finish("failed", action, after_result, error="UPS monitoring restore command failed.")
        elif self._abort_requested:
            self._finish("aborted", action, return_code)
        elif return_code == 0:
            self._finish("completed", action, return_code)
        elif return_code is not None and return_code < 0:
            self._finish("failed", action, return_code, error="Diagnostic command was terminated.")
        else:
            self._finish("failed", action, return_code)

    def _run_simple_command(self, label: str, command: list[str], timeout_seconds: int) -> int:
        self._append_output(f"{label}: {' '.join(command)}")
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self._append_output(str(exc))
            return 1
        for line in result.stdout.splitlines():
            self._append_output(line)
        for line in result.stderr.splitlines():
            self._append_output(line)
        return result.returncode

    def _force_stop_if_needed(self, process: subprocess.Popen[str]) -> None:
        try:
            process.wait(timeout=15)
            return
        except subprocess.TimeoutExpired:
            self._append_output("Diagnostic did not exit after abort input; terminating process.")
        try:
            process.terminate()
            process.wait(timeout=10)
            return
        except (OSError, subprocess.TimeoutExpired):
            self._append_output("Diagnostic did not terminate cleanly; killing process.")
        try:
            process.kill()
        except OSError:
            pass

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
