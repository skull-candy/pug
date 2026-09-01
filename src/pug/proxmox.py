from __future__ import annotations

import json
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pug.config import PowerActionsConfig


class ProxmoxError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProxmoxServer:
    name: str
    host: str
    node: str
    token_id: str
    token_secret_file: str
    order: int

    @classmethod
    def parse(cls, value: str) -> "ProxmoxServer":
        name, host, node, token_id, secret_file, order = value.split("|")
        return cls(name.strip(), host.strip(), node.strip(), token_id.strip(), secret_file.strip(), int(order))


class ProxmoxClient:
    def __init__(self, server: ProxmoxServer, config: PowerActionsConfig) -> None:
        self.server = server
        self.timeout = config.request_timeout_seconds
        if config.verify_tls:
            self.context = ssl.create_default_context(cafile=config.ca_certificate_path or None)
        else:
            self.context = ssl._create_unverified_context()  # noqa: SLF001 - explicit administrator option

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, values: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, values)

    def preflight(self) -> dict[str, Any]:
        cluster = self.get("/cluster/status")
        nodes = [item for item in cluster if item.get("type") == "node"]
        cluster_row = next((item for item in cluster if item.get("type") == "cluster"), {})
        online = [item for item in nodes if item.get("online") == 1]
        quorum = bool(cluster_row.get("quorate", 1))
        try:
            ha = self.get("/cluster/ha/status/current")
        except ProxmoxError:
            ha = []
        storage_healthy = True
        for node in online:
            try:
                storage = self.get(f"/nodes/{node['name']}/storage")
                storage_healthy = storage_healthy and all(item.get("active", 1) == 1 for item in storage if item.get("enabled", 1) == 1)
            except ProxmoxError:
                storage_healthy = False
        ceph_present = False
        ceph_healthy = True
        try:
            ceph = self.get("/cluster/ceph/status")
            ceph_present = bool(ceph)
            health = (ceph or {}).get("health", {})
            ceph_healthy = health.get("status", "HEALTH_OK") == "HEALTH_OK"
        except ProxmoxError:
            pass
        return {"quorum": quorum, "nodes": nodes, "online_nodes": online, "ha": ha, "ha_state": _ha_stack_state(ha), "storage_healthy": storage_healthy, "ceph_present": ceph_present, "ceph_healthy": ceph_healthy}

    def disarm_ha(self, mode: str) -> Any:
        return self.post("/cluster/ha/status/disarm-ha", {"resource-mode": mode})

    def arm_ha(self) -> Any:
        return self.post("/cluster/ha/status/arm-ha")

    def wait_for_ha_state(self, expected: str, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = self.preflight()
            if last["ha_state"] == expected:
                return last
            time.sleep(2)
        raise ProxmoxError(f"HA did not reach {expected} state before timeout; last state was {last.get('ha_state', 'unknown')}")

    def shutdown_node(self) -> Any:
        return self.post(f"/nodes/{self.server.node}/status", {"command": "shutdown"})

    def _request(self, method: str, path: str, values: dict[str, Any] | None = None) -> Any:
        token = Path(self.server.token_secret_file).read_text(encoding="utf-8").strip()
        if not token:
            raise ProxmoxError(f"empty token secret for {self.server.name}")
        data = urlencode(values or {}).encode() if values is not None else None
        request = Request(
            f"https://{self.server.host}:8006/api2/json{path}",
            data=data,
            method=method,
            headers={"Authorization": f"PVEAPIToken={self.server.token_id}={token}", "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(request, timeout=self.timeout, context=self.context) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload.get("data")
        except (HTTPError, URLError, OSError, ValueError) as exc:
            raise ProxmoxError(f"{self.server.name}: {exc}") from exc


def configured_servers(config: PowerActionsConfig) -> list[ProxmoxServer]:
    return sorted((ProxmoxServer.parse(value) for value in config.proxmox_servers), key=lambda item: item.order, reverse=True)


def _ha_stack_state(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("fencing", "fencing_status", "ha_state"):
            candidate = str(value.get(key, "")).lower()
            if candidate in {"armed", "disarmed", "disarming", "standby"}:
                return candidate
        for item in value.values():
            found = _ha_stack_state(item)
            if found != "unknown":
                return found
    if isinstance(value, list):
        for item in value:
            found = _ha_stack_state(item)
            if found != "unknown":
                return found
    return "unknown"
