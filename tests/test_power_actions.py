from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pug.config import AppConfig, ConfigError, PowerActionsConfig, validate_config
from pug.power_actions import PowerActionManager
from pug.proxmox import ProxmoxClient, ProxmoxServer, _ha_stack_state, configured_servers
from pug.state import StateStore, UPSState


def power_config(tmp_path, **changes) -> AppConfig:
    policy = replace(PowerActionsConfig(),
        enabled=True,
        armed=True,
        dry_run=True,
        minimum_on_battery_seconds=1,
        battery_charge_percent=30,
        runtime_minutes=10,
        consecutive_samples=2,
        state_file_path=str(tmp_path / "power-actions.json"),
        **changes,
    )
    return AppConfig(power_actions=policy)


def test_policy_requires_sustained_threshold_and_consecutive_samples(tmp_path, monkeypatch) -> None:
    config = power_config(tmp_path)
    state = UPSState(on_battery=True, battery_charge_percent=20, runtime_minutes=8, last_update=datetime.now(timezone.utc))
    manager = PowerActionManager(StateStore(state), lambda: config)
    manager._set(outage_started_at=(datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(), phase="pending")
    calls = []
    monkeypatch.setattr(manager, "start_shutdown", lambda manual=False, emergency=False: calls.append((manual, emergency)) or True)

    manager.evaluate(state)
    assert calls == []
    manager.evaluate(state)
    assert calls == [(False, False)]


def test_stale_ups_state_never_triggers(tmp_path, monkeypatch) -> None:
    config = power_config(tmp_path, maximum_state_age_seconds=2)
    state = UPSState(on_battery=True, battery_charge_percent=1, runtime_minutes=1, last_update=datetime.now(timezone.utc) - timedelta(minutes=1))
    manager = PowerActionManager(StateStore(state), lambda: config)
    calls = []
    monkeypatch.setattr(manager, "start_shutdown", lambda **kwargs: calls.append(kwargs))

    manager.evaluate(state)

    assert manager.snapshot().phase == "stale"
    assert calls == []


def test_manual_rearm_requires_power_restoration_and_pug_disarm_record(tmp_path) -> None:
    config = power_config(tmp_path)
    state = UPSState(on_battery=True, last_update=datetime.now(timezone.utc))
    manager = PowerActionManager(StateStore(state), lambda: config)

    assert manager.rearm_ha() is False
    assert "PUG did not disarm" in manager.snapshot().message


def test_proxmox_servers_are_parsed_and_sorted_by_shutdown_order() -> None:
    config = PowerActionsConfig(
        proxmox_servers=[
            "pve-1|10.0.0.1|pve-1|pug@pve!ups|/secret/one|10",
            "pve-2|10.0.0.2|pve-2|pug@pve!ups|/secret/two|30",
        ]
    )

    servers = configured_servers(config)

    assert [server.name for server in servers] == ["pve-2", "pve-1"]
    assert ProxmoxServer.parse(config.proxmox_servers[0]).node == "pve-1"


def test_config_rejects_bad_server_definition() -> None:
    config = AppConfig(power_actions=PowerActionsConfig(proxmox_servers=["not|enough|fields"]))

    with pytest.raises(ConfigError, match="proxmox_servers"):
        validate_config(config)


def test_ha_stack_state_detects_existing_administrator_disarm() -> None:
    assert _ha_stack_state([{"type": "fencing", "fencing": "disarmed"}]) == "disarmed"
    assert _ha_stack_state([{"type": "service", "status": "started"}]) == "unknown"


def test_proxmox_shutdown_uses_api_token_and_node_endpoint(tmp_path, monkeypatch) -> None:
    secret = tmp_path / "token"
    secret.write_text("top-secret\n", encoding="utf-8")
    server = ProxmoxServer("pve-1", "10.0.0.1", "node-a", "pug@pve!ups", str(secret), 1)
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"data":"UPID:test"}'

    def fake_urlopen(request, timeout, context):
        requests.append((request, timeout, context))
        return Response()

    monkeypatch.setattr("pug.proxmox.urlopen", fake_urlopen)
    client = ProxmoxClient(server, PowerActionsConfig(verify_tls=False))

    assert client.shutdown_node() == "UPID:test"
    request = requests[0][0]
    assert request.full_url.endswith("/nodes/node-a/status")
    assert request.headers["Authorization"] == "PVEAPIToken=pug@pve!ups=top-secret"
    assert request.data == b"command=shutdown"
