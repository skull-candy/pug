from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pug.config import AppConfig
from pug.notifications import NotificationManager
from pug.proxmox import ProxmoxClient, ProxmoxError, configured_servers
from pug.state import StateStore, UPSState

LOGGER = logging.getLogger(__name__)


@dataclass
class PowerActionSnapshot:
    phase: str = "disabled"
    message: str = "Power actions are disabled."
    outage_started_at: str = ""
    online_since: str = ""
    recovery_healthy_since: str = ""
    triggered_at: str = ""
    completed_at: str = ""
    pug_disarmed_ha: bool = False
    ha_state: str = "unknown"
    consecutive_samples: int = 0
    event_log: list[dict[str, str]] = field(default_factory=list)
    node_results: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PowerActionManager:
    def __init__(self, store: StateStore, config_provider: Callable[[], AppConfig]) -> None:
        self.store = store
        self.config_provider = config_provider
        self.notifications = NotificationManager()
        self._lock = threading.Lock()
        self._snapshot = PowerActionSnapshot()
        self._running = False
        self._load()

    def snapshot(self) -> PowerActionSnapshot:
        with self._lock:
            return PowerActionSnapshot(**json.loads(json.dumps(self._snapshot.to_dict())))

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.evaluate(self.store.get())
            except Exception:
                LOGGER.exception("power action evaluation failed")
            stop.wait(2)

    def evaluate(self, state: UPSState) -> None:
        config = self.config_provider()
        policy = config.power_actions
        now = datetime.now(timezone.utc)
        if not policy.enabled or not policy.armed:
            self._set(phase="disabled", message="Power actions are disabled or disarmed.", consecutive_samples=0)
            return
        age = (now - state.last_update).total_seconds()
        if age > policy.maximum_state_age_seconds:
            self._set(phase="stale", message=f"UPS data is stale ({age:.0f}s).", consecutive_samples=0)
            return
        snap = self.snapshot()
        if state.on_battery:
            if not snap.outage_started_at:
                self._set(outage_started_at=now.isoformat(), online_since="", phase="on_battery", message="Utility power lost; evaluating shutdown policy.")
                self._event(config, "power_lost", "warning", "UPS is running on battery.", state)
                snap = self.snapshot()
            if snap.triggered_at:
                return
            elapsed = (now - _parse_time(snap.outage_started_at)).total_seconds()
            thresholds = [state.battery_charge_percent <= policy.battery_charge_percent, state.runtime_minutes <= policy.runtime_minutes]
            threshold_met = all(thresholds) if policy.threshold_mode == "all" else any(thresholds)
            samples = snap.consecutive_samples + 1 if elapsed >= policy.minimum_on_battery_seconds and threshold_met else 0
            self._set(phase="pending", message=f"On battery for {elapsed:.0f}s; threshold {'met' if threshold_met else 'not met'}.", consecutive_samples=samples)
            emergency = policy.emergency_enabled and (state.battery_charge_percent <= policy.emergency_battery_charge_percent or state.runtime_minutes <= policy.emergency_runtime_minutes)
            if not snap.triggered_at and (samples >= policy.consecutive_samples or emergency):
                self.start_shutdown(manual=False, emergency=emergency)
            return

        if snap.outage_started_at:
            if not snap.online_since:
                self._set(online_since=now.isoformat(), phase="power_restored", message="Utility power restored; waiting for stable power.", consecutive_samples=0)
                self._event(config, "power_restored", "info", "Utility power has been restored.", state)
                snap = self.snapshot()
            stable = (now - _parse_time(snap.online_since)).total_seconds()
            if snap.pug_disarmed_ha:
                if policy.ha_recovery_mode == "automatic_safe" and stable >= policy.rearm_after_online_seconds:
                    if self._recovery_ready(config):
                        refreshed = self.snapshot()
                        if not refreshed.recovery_healthy_since:
                            self._set(recovery_healthy_since=now.isoformat(), phase="recovery_stabilizing", message="Cluster is healthy; waiting for the HA health stabilization period.")
                        elif (now - _parse_time(refreshed.recovery_healthy_since)).total_seconds() >= policy.ha_health_stable_seconds:
                            self.rearm_ha(manual=False)
                    else:
                        self._set(recovery_healthy_since="", phase="recovery_waiting", message="Waiting for Proxmox recovery health checks.")
                elif policy.ha_recovery_mode == "manual":
                    self._set(phase="awaiting_manual_rearm", message="Power is stable; HA requires manual rearming.")
                else:
                    self._set(phase="ha_left_disarmed", message="HA recovery policy is leave_disarmed.")
            elif stable >= policy.rearm_after_online_seconds:
                self._set(phase="monitoring", message="Utility power is stable; shutdown policy rearmed.", outage_started_at="", online_since="", recovery_healthy_since="", triggered_at="", completed_at="", consecutive_samples=0, node_results={})
        else:
            self._set(phase="monitoring", message="Monitoring UPS shutdown criteria.")

    def start_shutdown(self, manual: bool = False, emergency: bool = False) -> bool:
        config = self.config_provider()
        if not config.power_actions.enabled or (not manual and not config.power_actions.armed):
            return False
        with self._lock:
            if self._running or self._snapshot.triggered_at:
                return False
            self._running = True
            self._snapshot.triggered_at = datetime.now(timezone.utc).isoformat()
            self._snapshot.phase = "dry_run" if config.power_actions.dry_run else "preflight"
            self._snapshot.message = "Shutdown workflow started."
            self._save_locked(config)
        threading.Thread(target=self._shutdown, args=(config, emergency), name="proxmox-shutdown", daemon=True).start()
        return True

    def rearm_ha(self, manual: bool = True) -> bool:
        config = self.config_provider()
        snap = self.snapshot()
        if config.power_actions.rearm_only_if_pug_disarmed_ha and not snap.pug_disarmed_ha:
            self._set(message="Refusing to rearm HA because PUG did not disarm it.")
            return False
        state = self.store.get()
        if state.on_battery or not snap.online_since:
            self._set(message="Refusing to rearm HA until utility power is restored.")
            return False
        stable = (datetime.now(timezone.utc) - _parse_time(snap.online_since)).total_seconds()
        if stable < config.power_actions.rearm_after_online_seconds:
            self._set(message=f"Refusing to rearm HA until power is stable for {config.power_actions.rearm_after_online_seconds} seconds.")
            return False
        with self._lock:
            if self._running:
                return False
            self._running = True
        try:
            server = configured_servers(config.power_actions)[0]
            client = ProxmoxClient(server, config.power_actions)
            check = client.preflight()
            if config.power_actions.ha_require_quorum and not check["quorum"]:
                raise ProxmoxError("cluster is not quorate")
            if config.power_actions.ha_require_all_nodes and len(check["online_nodes"]) != len(check["nodes"]):
                raise ProxmoxError("not all cluster nodes are online")
            if config.power_actions.ha_require_storage_healthy and not check["storage_healthy"]:
                raise ProxmoxError("cluster storage is not healthy")
            if config.power_actions.ha_require_ceph_healthy and check["ceph_present"] and not check["ceph_healthy"]:
                raise ProxmoxError("Ceph is not healthy")
            if not config.power_actions.dry_run:
                client.arm_ha()
                client.wait_for_ha_state("armed", config.power_actions.request_timeout_seconds * 6)
            self._set(phase="monitoring", message="HA rearmed successfully." if not config.power_actions.dry_run else "Dry run: HA would be rearmed.", pug_disarmed_ha=False, ha_state="armed", outage_started_at="", online_since="", recovery_healthy_since="", triggered_at="", completed_at="")
            self._event(config, "ha_rearmed", "info", "Proxmox HA was rearmed after power recovery.")
            return True
        except (ProxmoxError, IndexError, OSError, ValueError) as exc:
            self._set(phase="rearm_failed", message=str(exc))
            self._event(config, "ha_rearm_failed", "critical", str(exc))
            return False
        finally:
            with self._lock:
                self._running = False

    def test_notifications(self) -> list[dict[str, Any]]:
        config = self.config_provider()
        return [asdict(item) for item in self.notifications.send(config.notifications, "test_notification", "warning", "PowerPi UPS Gateway notification test.")]

    def reset_latch(self) -> None:
        self._set(phase="monitoring", message="Shutdown latch reset.", outage_started_at="", online_since="", recovery_healthy_since="", triggered_at="", completed_at="", consecutive_samples=0, node_results={})

    def _shutdown(self, config: AppConfig, emergency: bool) -> None:
        policy = config.power_actions
        try:
            servers = configured_servers(policy)
            if not servers:
                raise ProxmoxError("no Proxmox servers configured")
            self._event(config, "shutdown_started", "critical", "Proxmox shutdown workflow started.", self.store.get())
            client = ProxmoxClient(servers[0], policy)
            preflight = client.preflight()
            safe = (
                (not policy.ha_require_quorum or preflight["quorum"])
                and (not policy.ha_require_all_nodes or len(preflight["online_nodes"]) == len(preflight["nodes"]))
                and (not policy.ha_require_storage_healthy or preflight["storage_healthy"])
                and (not policy.ha_require_ceph_healthy or not preflight["ceph_present"] or preflight["ceph_healthy"])
            )
            if not safe and not (emergency and policy.proceed_if_ha_preflight_failed):
                raise ProxmoxError("HA preflight failed: quorum or required nodes unavailable")
            ha_configured = bool(preflight["ha"])
            if ha_configured and policy.ha_disarm_before_shutdown:
                if preflight["ha_state"] in {"disarmed", "disarming"}:
                    self._set(pug_disarmed_ha=False, ha_state=preflight["ha_state"], phase="ha_already_disarmed", message="HA was already disarmed; PUG will not rearm it later.")
                    self._event(config, "ha_already_disarmed", "warning", "HA was already disarmed before the shutdown workflow.")
                else:
                    if not policy.dry_run:
                        client.disarm_ha(policy.ha_disarm_mode)
                        client.wait_for_ha_state("disarmed", policy.request_timeout_seconds * 6)
                    self._set(pug_disarmed_ha=True, ha_state=f"disarmed:{policy.ha_disarm_mode}", phase="ha_disarmed", message=f"HA {'would be ' if policy.dry_run else ''}disarmed in {policy.ha_disarm_mode} mode.")
                    self._event(config, "ha_disarmed", "critical", f"HA disarmed in {policy.ha_disarm_mode} mode for cluster shutdown.")
            for server in servers:
                if policy.dry_run:
                    result = "dry-run: shutdown would be requested"
                else:
                    ProxmoxClient(server, policy).shutdown_node()
                    result = "shutdown requested"
                results = self.snapshot().node_results
                results[server.name] = result
                self._set(phase="shutting_down", message=f"{server.name}: {result}", node_results=results)
                if not policy.dry_run and policy.delay_between_nodes_seconds > 0 and server is not servers[-1]:
                    time.sleep(policy.delay_between_nodes_seconds)
            self._set(phase="completed", message="Proxmox shutdown workflow completed.", completed_at=datetime.now(timezone.utc).isoformat())
            self._event(config, "shutdown_completed", "critical", "All configured Proxmox shutdown requests were processed.")
        except (ProxmoxError, OSError, ValueError) as exc:
            self._set(phase="failed", message=str(exc))
            self._event(config, "shutdown_failed", "critical", str(exc), self.store.get())
        finally:
            with self._lock:
                self._running = False

    def _recovery_ready(self, config: AppConfig) -> bool:
        try:
            server = configured_servers(config.power_actions)[0]
            check = ProxmoxClient(server, config.power_actions).preflight()
        except (ProxmoxError, IndexError, OSError, ValueError):
            return False
        policy = config.power_actions
        return (
            (not policy.ha_require_quorum or check["quorum"])
            and (not policy.ha_require_all_nodes or len(check["online_nodes"]) == len(check["nodes"]))
            and (not policy.ha_require_storage_healthy or check["storage_healthy"])
            and (not policy.ha_require_ceph_healthy or not check["ceph_present"] or check["ceph_healthy"])
        )

    def _event(self, config: AppConfig, event: str, severity: str, message: str, state: UPSState | None = None) -> None:
        details: dict[str, Any] = {}
        if state:
            details = {"ups": state.name, "charge": f"{state.battery_charge_percent}%", "runtime": f"{state.runtime_minutes} min", "status": state.status_text}
        results = self.notifications.send(config.notifications, event, severity, message, details)
        row = {"time": datetime.now(timezone.utc).isoformat(), "event": event, "severity": severity, "message": message, "notifications": ", ".join(f"{item.provider}:{'ok' if item.ok else 'failed'}" for item in results)}
        with self._lock:
            self._snapshot.event_log = [*self._snapshot.event_log, row][-100:]
            self._save_locked(config)

    def _set(self, **values: Any) -> None:
        config = self.config_provider()
        with self._lock:
            for key, value in values.items():
                setattr(self._snapshot, key, value)
            self._save_locked(config)

    def _load(self) -> None:
        try:
            path = Path(self.config_provider().power_actions.state_file_path)
            if path.exists():
                self._snapshot = PowerActionSnapshot(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            LOGGER.exception("failed to load power action state")

    def _save_locked(self, config: AppConfig) -> None:
        path = Path(config.power_actions.state_file_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(json.dumps(self._snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
            temporary.replace(path)
        except OSError:
            LOGGER.exception("failed to persist power action state to %s", path)


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
