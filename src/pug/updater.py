from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PUBLIC_REPO_URL = "https://git.vns.ae/ahsan/pug"
SERVICE_NAME = "powerpi-ups-gateway"


@dataclass(frozen=True)
class UpdateSnapshot:
    status: str = "idle"
    update_available: bool = False
    current_commit: str = ""
    latest_commit: str = ""
    branch: str = ""
    remote: str = PUBLIC_REPO_URL
    checked_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "update_available": self.update_available,
            "current_commit": self.current_commit,
            "latest_commit": self.latest_commit,
            "branch": self.branch,
            "remote": self.remote,
            "checked_at": self.checked_at.isoformat() if self.checked_at else "",
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "finished_at": self.finished_at.isoformat() if self.finished_at else "",
            "output": list(self.output),
            "error": self.error,
        }


class UpdateManager:
    def __init__(self, repo_path: str | Path | None = None) -> None:
        self.repo_path = Path(repo_path) if repo_path else Path(__file__).resolve().parents[2]
        self._lock = threading.Lock()
        self._snapshot = UpdateSnapshot(remote=PUBLIC_REPO_URL)

    def run_background_checks(self, stop: threading.Event, interval_seconds: int = 3600, initial_delay_seconds: int = 15) -> None:
        if stop.wait(initial_delay_seconds):
            return
        while not stop.is_set():
            snapshot = self.snapshot()
            if snapshot.status != "installing":
                self.check()
            stop.wait(interval_seconds)

    def snapshot(self) -> UpdateSnapshot:
        with self._lock:
            return UpdateSnapshot(
                status=self._snapshot.status,
                update_available=self._snapshot.update_available,
                current_commit=self._snapshot.current_commit,
                latest_commit=self._snapshot.latest_commit,
                branch=self._snapshot.branch,
                remote=self._snapshot.remote,
                checked_at=self._snapshot.checked_at,
                started_at=self._snapshot.started_at,
                finished_at=self._snapshot.finished_at,
                output=list(self._snapshot.output),
                error=self._snapshot.error,
            )

    def check(self) -> UpdateSnapshot:
        self._set(status="checking", error="", output=["Checking for updates..."])
        try:
            result = check_for_update(self.repo_path)
        except Exception as exc:
            self._set(status="failed", error=str(exc), finished_at=datetime.now(timezone.utc))
            return self.snapshot()
        self._set(
            status="available" if result["update_available"] else "current",
            update_available=result["update_available"],
            current_commit=result["current_commit"],
            latest_commit=result["latest_commit"],
            branch=result["branch"],
            remote=result["remote"],
            checked_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            output=[
                f"Remote: {result['remote']}",
                f"Branch: {result['branch']}",
                f"Current commit: {result['current_commit']}",
                f"Latest commit: {result['latest_commit']}",
            ],
        )
        return self.snapshot()

    def start_install(self) -> bool:
        with self._lock:
            if self._snapshot.status == "installing":
                return False
            self._snapshot = UpdateSnapshot(
                status="installing",
                update_available=self._snapshot.update_available,
                current_commit=self._snapshot.current_commit,
                latest_commit=self._snapshot.latest_commit,
                branch=self._snapshot.branch,
                remote=self._snapshot.remote,
                checked_at=self._snapshot.checked_at,
                started_at=datetime.now(timezone.utc),
                output=["Starting update install..."],
            )
        thread = threading.Thread(target=self._install, name="updater", daemon=True)
        thread.start()
        return True

    def _install(self) -> None:
        try:
            result = install_update(self.repo_path, self._append)
        except Exception as exc:
            self._set(status="failed", error=str(exc), finished_at=datetime.now(timezone.utc))
            return
        self._set(
            status="installed",
            update_available=False,
            current_commit=result["current_commit"],
            latest_commit=result["latest_commit"],
            branch=result["branch"],
            remote=result["remote"],
            finished_at=datetime.now(timezone.utc),
        )
        self._append("Update installed. Restarting service if systemd is available...")
        threading.Thread(target=restart_service_later, daemon=True).start()

    def _append(self, line: str) -> None:
        with self._lock:
            output = [*self._snapshot.output, line][-400:]
            self._snapshot = self._replace(output=output)

    def _set(self, **changes: Any) -> None:
        with self._lock:
            self._snapshot = self._replace(**changes)

    def _replace(self, **changes: Any) -> UpdateSnapshot:
        data = self._snapshot.to_dict()
        data["checked_at"] = self._snapshot.checked_at
        data["started_at"] = self._snapshot.started_at
        data["finished_at"] = self._snapshot.finished_at
        data.update(changes)
        return UpdateSnapshot(**data)


def check_for_update(repo_path: Path) -> dict[str, Any]:
    ensure_git_repo(repo_path)
    remote = remote_url(repo_path)
    branch = current_branch(repo_path)
    run_git(repo_path, ["fetch", "origin", "--prune"])
    remote_ref = best_remote_ref(repo_path, branch)
    current = run_git(repo_path, ["rev-parse", "--short", "HEAD"]).stdout.strip()
    latest = run_git(repo_path, ["rev-parse", "--short", remote_ref]).stdout.strip()
    return {
        "remote": remote,
        "branch": branch,
        "current_commit": current,
        "latest_commit": latest,
        "update_available": current != latest,
    }


def install_update(repo_path: Path, log: Any) -> dict[str, Any]:
    ensure_git_repo(repo_path)
    branch = current_branch(repo_path)
    remote_ref = best_remote_ref(repo_path, branch)
    log("Fetching latest source...")
    run_git(repo_path, ["fetch", "origin", "--prune"])
    log(f"Fast-forwarding {branch} from {remote_ref}...")
    run_git(repo_path, ["merge", "--ff-only", remote_ref])
    log("Installing package with current Python...")
    run_command([sys.executable, "-m", "pip", "install", "-e", str(repo_path)], repo_path)
    return check_for_update(repo_path)


def ensure_git_repo(repo_path: Path) -> None:
    if not (repo_path / ".git").exists():
        raise RuntimeError(f"{repo_path} is not a git checkout")
    if not remote_url(repo_path):
        run_git(repo_path, ["remote", "add", "origin", PUBLIC_REPO_URL])
    elif remote_url(repo_path) != PUBLIC_REPO_URL:
        run_git(repo_path, ["remote", "set-url", "origin", PUBLIC_REPO_URL])


def remote_url(repo_path: Path) -> str:
    result = run_git(repo_path, ["config", "--get", "remote.origin.url"], check=False)
    return result.stdout.strip() or PUBLIC_REPO_URL


def current_branch(repo_path: Path) -> str:
    result = run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    branch = result.stdout.strip()
    return "main" if branch == "HEAD" else branch


def best_remote_ref(repo_path: Path, branch: str) -> str:
    candidates = [f"origin/{branch}", "origin/main", "origin/master"]
    for candidate in candidates:
        result = run_git(repo_path, ["rev-parse", "--verify", candidate], check=False)
        if result.returncode == 0:
            return candidate
    raise RuntimeError("No usable origin branch was found after fetch")


def run_git(repo_path: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command(["git", "-C", str(repo_path), *args], repo_path, check=check)


def run_command(command: list[str], repo_path: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=repo_path, capture_output=True, text=True, timeout=300)
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"command failed: {' '.join(command)}"
        raise RuntimeError(message)
    return result


def restart_service_later() -> None:
    time.sleep(2)
    subprocess.run(["systemctl", "restart", SERVICE_NAME], capture_output=True, text=True, timeout=60)
