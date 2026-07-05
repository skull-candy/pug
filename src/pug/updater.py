from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

from pug import __version__
from pug.config import AppConfig, ConfigError, UpdateConfig, load_config, save_config

LOGGER = logging.getLogger(__name__)

DEFAULT_GITLAB_BASE_URL = "https://git.vns.ae"
DEFAULT_GITLAB_PROJECT_PATH = "ahsan/pug"
PUBLIC_REPO_URL = "https://git.vns.ae/ahsan/pug"
SERVICE_NAME = "powerpi-ups-gateway"


@dataclass(frozen=True)
class UpdateSnapshot:
    status: str = "idle"
    update_available: bool = False
    installed_version: str = __version__
    latest_version: str = ""
    latest_release_url: str = ""
    latest_release_name: str = ""
    gitlab_base_url: str = DEFAULT_GITLAB_BASE_URL
    project_path: str = DEFAULT_GITLAB_PROJECT_PATH
    check_interval: str = "7d"
    checked_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "update_available": self.update_available,
            "installed_version": self.installed_version,
            "latest_version": self.latest_version,
            "latest_release_url": self.latest_release_url,
            "latest_release_name": self.latest_release_name,
            "gitlab_base_url": self.gitlab_base_url,
            "project_path": self.project_path,
            "check_interval": self.check_interval,
            "checked_at": self.checked_at.isoformat() if self.checked_at else "",
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "finished_at": self.finished_at.isoformat() if self.finished_at else "",
            "output": list(self.output),
            "error": self.error,
        }


class UpdateManager:
    def __init__(self, config_path: str | Path | None = None, config: AppConfig | None = None, repo_path: str | Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path else None
        self._default_config = config or AppConfig()
        self.repo_path = Path(repo_path) if repo_path else Path(__file__).resolve().parents[2]
        self._lock = threading.Lock()
        self._snapshot = snapshot_from_config(self._load_config())

    def run_background_checks(self, stop: threading.Event, poll_seconds: int = 3600, initial_delay_seconds: int = 15) -> None:
        if stop.wait(initial_delay_seconds):
            return
        while not stop.is_set():
            snapshot = self.snapshot()
            if snapshot.status != "installing":
                self.check_if_due()
            stop.wait(poll_seconds)

    def snapshot(self) -> UpdateSnapshot:
        with self._lock:
            return UpdateSnapshot(
                status=self._snapshot.status,
                update_available=self._snapshot.update_available,
                installed_version=self._snapshot.installed_version,
                latest_version=self._snapshot.latest_version,
                latest_release_url=self._snapshot.latest_release_url,
                latest_release_name=self._snapshot.latest_release_name,
                gitlab_base_url=self._snapshot.gitlab_base_url,
                project_path=self._snapshot.project_path,
                check_interval=self._snapshot.check_interval,
                checked_at=self._snapshot.checked_at,
                started_at=self._snapshot.started_at,
                finished_at=self._snapshot.finished_at,
                output=list(self._snapshot.output),
                error=self._snapshot.error,
            )

    def check_if_due(self) -> bool:
        config = self._load_config()
        self._refresh_from_config(config)
        if config.update.check_interval == "off":
            self._set(status="disabled", update_available=False, error="")
            return False
        if not update_check_due(config.update):
            return False
        self.check(config)
        return True

    def check(self, config: AppConfig | None = None) -> UpdateSnapshot:
        config = config or self._load_config()
        self._refresh_from_config(config)
        if config.update.check_interval == "off":
            self._set(status="disabled", update_available=False, error="")
            return self.snapshot()
        self._set(status="checking", error="", output=["Checking GitLab Releases..."])
        checked_at = datetime.now(timezone.utc)
        try:
            result = check_for_update(config.update)
        except Exception as exc:
            LOGGER.info("GitLab release update check failed: %s", exc)
            self._set(status="idle", checked_at=checked_at, finished_at=checked_at, error="", output=[])
            self._store_update_metadata(config, checked_at=checked_at)
            return self.snapshot()
        latest_version = result["latest_version"]
        update_available = is_newer_version(latest_version, __version__)
        self._set(
            status="available" if update_available else "current",
            update_available=update_available,
            latest_version=latest_version,
            latest_release_url=result["latest_release_url"],
            latest_release_name=result["latest_release_name"],
            gitlab_base_url=config.update.gitlab_base_url,
            project_path=config.update.project_path,
            check_interval=config.update.check_interval,
            checked_at=checked_at,
            finished_at=checked_at,
            output=[
                f"Installed version: {__version__}",
                f"Latest release: {latest_version}",
                f"Release page: {result['latest_release_url'] or '-'}",
            ],
        )
        self._store_update_metadata(
            config,
            checked_at=checked_at,
            latest_version=latest_version,
            latest_release_url=result["latest_release_url"],
            latest_release_name=result["latest_release_name"],
        )
        return self.snapshot()

    def start_install(self) -> bool:
        with self._lock:
            if self._snapshot.status == "installing":
                return False
            self._snapshot = replace(
                self._snapshot,
                status="installing",
                started_at=datetime.now(timezone.utc),
                output=["Starting update install..."],
            )
        thread = threading.Thread(target=self._install, name="updater", daemon=True)
        thread.start()
        return True

    def _install(self) -> None:
        try:
            install_update(self.repo_path, self._append)
        except Exception as exc:
            self._set(status="failed", error=str(exc), finished_at=datetime.now(timezone.utc))
            return
        self._set(status="installed", update_available=False, finished_at=datetime.now(timezone.utc))
        self._append("Update installed. Restarting service if systemd is available...")
        threading.Thread(target=restart_service_later, daemon=True).start()

    def _load_config(self) -> AppConfig:
        if self.config_path:
            try:
                return load_config(self.config_path)
            except (ConfigError, OSError) as exc:
                LOGGER.info("failed to load update config: %s", exc)
        return self._default_config

    def _refresh_from_config(self, config: AppConfig) -> None:
        current = snapshot_from_config(config)
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                update_available=current.update_available,
                latest_version=current.latest_version,
                latest_release_url=current.latest_release_url,
                latest_release_name=current.latest_release_name,
                gitlab_base_url=current.gitlab_base_url,
                project_path=current.project_path,
                check_interval=current.check_interval,
                checked_at=current.checked_at or self._snapshot.checked_at,
            )

    def _store_update_metadata(
        self,
        config: AppConfig,
        checked_at: datetime,
        latest_version: str | None = None,
        latest_release_url: str | None = None,
        latest_release_name: str | None = None,
    ) -> None:
        if not self.config_path:
            return
        update = replace(
            config.update,
            last_update_check=checked_at.isoformat(),
            latest_version=latest_version if latest_version is not None else config.update.latest_version,
            latest_release_url=latest_release_url if latest_release_url is not None else config.update.latest_release_url,
            latest_release_name=latest_release_name if latest_release_name is not None else config.update.latest_release_name,
        )
        try:
            save_config(replace(config, update=update), self.config_path)
        except OSError as exc:
            LOGGER.info("failed to store update metadata: %s", exc)

    def _append(self, line: str) -> None:
        with self._lock:
            output = [*self._snapshot.output, line][-400:]
            self._snapshot = replace(self._snapshot, output=output)

    def _set(self, **changes: Any) -> None:
        with self._lock:
            self._snapshot = replace(self._snapshot, **changes)


def snapshot_from_config(config: AppConfig) -> UpdateSnapshot:
    latest_version = config.update.latest_version
    return UpdateSnapshot(
        status="disabled" if config.update.check_interval == "off" else "idle",
        update_available=bool(latest_version and is_newer_version(latest_version, __version__)),
        installed_version=__version__,
        latest_version=latest_version,
        latest_release_url=config.update.latest_release_url,
        latest_release_name=config.update.latest_release_name,
        gitlab_base_url=config.update.gitlab_base_url,
        project_path=config.update.project_path,
        check_interval=config.update.check_interval,
        checked_at=parse_datetime(config.update.last_update_check),
    )


def update_check_due(config: UpdateConfig, now: datetime | None = None) -> bool:
    if config.check_interval == "off":
        return False
    checked_at = parse_datetime(config.last_update_check)
    if checked_at is None:
        return True
    days = 1 if config.check_interval == "1d" else 7
    return (now or datetime.now(timezone.utc)) - checked_at >= timedelta(days=days)


def check_for_update(config: UpdateConfig) -> dict[str, str]:
    url = latest_release_api_url(config.gitlab_base_url, config.project_path)
    LOGGER.debug("Checking latest GitLab release from %s", url)
    with urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    tag_name = str(payload.get("tag_name", "")).strip()
    if not tag_name:
        raise RuntimeError("latest GitLab release response did not include tag_name")
    release_url = str(payload.get("_links", {}).get("self") or payload.get("url") or "")
    return {
        "latest_version": tag_name,
        "latest_release_url": release_url or release_page_url(config.gitlab_base_url, config.project_path, tag_name),
        "latest_release_name": str(payload.get("name") or tag_name),
    }


def latest_release_api_url(gitlab_base_url: str, project_path: str) -> str:
    return f"{gitlab_base_url.rstrip('/')}/api/v4/projects/{quote(project_path, safe='')}/releases/permalink/latest"


def release_page_url(gitlab_base_url: str, project_path: str, tag_name: str) -> str:
    return f"{gitlab_base_url.rstrip('/')}/{project_path.strip('/')}/-/releases/{quote(tag_name, safe='')}"


def is_newer_version(candidate: str, installed: str) -> bool:
    return compare_versions(candidate, installed) > 0


def compare_versions(left: str, right: str) -> int:
    left_version = parse_version(left)
    right_version = parse_version(right)
    if left_version[0] != right_version[0]:
        return 1 if left_version[0] > right_version[0] else -1
    return compare_prerelease(left_version[1], right_version[1])


def parse_version(value: str) -> tuple[tuple[int, ...], list[str]]:
    clean = value.strip()
    if clean.lower().startswith("v"):
        clean = clean[1:]
    clean = clean.split("+", 1)[0]
    tokens = re.findall(r"[0-9]+|[A-Za-z]+", clean)
    numbers: list[int] = []
    prerelease: list[str] = []
    in_prerelease = False
    for token in tokens:
        if token.isdigit() and not in_prerelease:
            numbers.append(int(token))
            continue
        in_prerelease = True
        prerelease.append(token.lower())
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers), prerelease


def compare_prerelease(left: list[str], right: list[str]) -> int:
    if not left and not right:
        return 0
    if not left:
        return 1
    if not right:
        return -1
    max_length = max(len(left), len(right))
    for index in range(max_length):
        left_token = left[index] if index < len(left) else "0"
        right_token = right[index] if index < len(right) else "0"
        result = compare_prerelease_token(left_token, right_token)
        if result != 0:
            return result
    return 0


def compare_prerelease_token(left: str, right: str) -> int:
    if left == right:
        return 0
    if left.isdigit() and right.isdigit():
        return 1 if int(left) > int(right) else -1
    ranks = {"a": 1, "alpha": 1, "b": 2, "beta": 2, "pre": 2, "preview": 2, "rc": 3}
    left_rank = ranks.get(left, 0)
    right_rank = ranks.get(right, 0)
    if left_rank != right_rank:
        return 1 if left_rank > right_rank else -1
    return 1 if left > right else -1


def parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def install_update(repo_path: Path, log: Any) -> None:
    ensure_git_repo(repo_path)
    branch = current_branch(repo_path)
    remote_ref = best_remote_ref(repo_path, branch)
    log("Fetching latest source...")
    run_git(repo_path, ["fetch", "origin", "--prune"])
    log(f"Fast-forwarding {branch} from {remote_ref}...")
    run_git(repo_path, ["merge", "--ff-only", remote_ref])
    log("Installing package with current Python...")
    run_command([sys.executable, "-m", "pip", "install", "-e", str(repo_path)], repo_path)


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
