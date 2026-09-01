from __future__ import annotations

from dataclasses import asdict, dataclass, field
import ipaddress
from pathlib import Path
import shlex
from typing import Any


class ConfigError(ValueError):
    """Raised when configuration is syntactically valid but unusable."""


@dataclass(frozen=True)
class BackendConfig:
    type: str = "apcupsd"
    command: list[str] = field(default_factory=lambda: ["apcaccess", "status", "localhost:3551"])
    poll_interval_seconds: float = 3.0


@dataclass(frozen=True)
class SnmpConfig:
    enabled: bool = True
    listen: str = "0.0.0.0"
    port: int = 161
    community: str = "public"
    developer_log: bool = True


@dataclass(frozen=True)
class HttpConfig:
    enabled: bool = True
    listen: str = "0.0.0.0"
    port: int = 8080
    api_enabled: bool = True
    prometheus_enabled: bool = True
    homeassistant_enabled: bool = True
    auth_mode: str = "disabled"
    auth_username: str = ""
    auth_password: str = ""
    auth_bypass_networks: list[str] = field(
        default_factory=lambda: [
            "127.0.0.0/8",
            "::1/128",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "fc00::/7",
            "fe80::/10",
        ]
    )


@dataclass(frozen=True)
class MqttConfig:
    enabled: bool = False
    host: str = "localhost"
    port: int = 1883
    client_id: str = "powerpi-ups-gateway"
    topic_prefix: str = "powerpi/ups"
    discovery_prefix: str = "homeassistant"
    username: str = ""
    password: str = ""
    publish_interval_seconds: float = 30.0


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    file_path: str = "/var/log/pug/pug.log"
    apcupsd_events_path: str = "/var/log/apcupsd.events"
    web_tail_lines: int = 300
    timezone: str = "UTC"


@dataclass(frozen=True)
class DiagnosticsConfig:
    before_command: list[str] = field(default_factory=lambda: ["systemctl", "stop", "apcupsd"])
    after_command: list[str] = field(default_factory=lambda: ["systemctl", "start", "apcupsd"])
    self_test_command: list[str] = field(default_factory=lambda: ["apctest"])
    self_test_selection: str = "2"
    battery_calibration_command: list[str] = field(default_factory=lambda: ["apctest"])
    battery_calibration_selection: str = "10"
    command_timeout_seconds: int = 21600


@dataclass(frozen=True)
class UpdateConfig:
    gitlab_base_url: str = "https://git.vns.ae"
    project_path: str = "ahsan/pug"
    check_interval: str = "7d"
    last_update_check: str = ""
    latest_version: str = ""
    latest_release_url: str = ""
    latest_release_name: str = ""


@dataclass(frozen=True)
class NotificationConfig:
    discord_enabled: bool = False
    discord_webhook_url_file: str = "/etc/pug/secrets/discord-webhook"
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"
    smtp_username: str = ""
    smtp_password_file: str = "/etc/pug/secrets/smtp-password"
    email_from: str = ""
    email_recipients: list[str] = field(default_factory=list)
    minimum_severity: str = "warning"
    timeout_seconds: int = 10


@dataclass(frozen=True)
class PowerActionsConfig:
    enabled: bool = False
    armed: bool = False
    dry_run: bool = True
    minimum_on_battery_seconds: int = 180
    battery_charge_percent: int = 30
    runtime_minutes: int = 10
    threshold_mode: str = "any"
    consecutive_samples: int = 3
    maximum_state_age_seconds: int = 15
    rearm_after_online_seconds: int = 600
    emergency_enabled: bool = True
    emergency_battery_charge_percent: int = 8
    emergency_runtime_minutes: int = 2
    proceed_if_ha_preflight_failed: bool = False
    proxmox_servers: list[str] = field(default_factory=list)
    verify_tls: bool = True
    ca_certificate_path: str = ""
    request_timeout_seconds: int = 10
    delay_between_nodes_seconds: int = 20
    ha_disarm_before_shutdown: bool = True
    ha_disarm_mode: str = "freeze"
    ha_recovery_mode: str = "manual"
    ha_require_all_nodes: bool = True
    ha_require_quorum: bool = True
    ha_require_storage_healthy: bool = True
    ha_require_ceph_healthy: bool = True
    ha_health_stable_seconds: int = 120
    rearm_only_if_pug_disarmed_ha: bool = True
    state_file_path: str = "/var/lib/pug/power-actions.json"


@dataclass(frozen=True)
class AppConfig:
    backend: BackendConfig = field(default_factory=BackendConfig)
    snmp: SnmpConfig = field(default_factory=SnmpConfig)
    http: HttpConfig = field(default_factory=HttpConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    diagnostics: DiagnosticsConfig = field(default_factory=DiagnosticsConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    power_actions: PowerActionsConfig = field(default_factory=PowerActionsConfig)


def load_config(path: str | Path | None) -> AppConfig:
    data: dict[str, Any] = {}
    if path:
        config_path = Path(path)
        if config_path.exists():
            data = _parse_simple_yaml(config_path.read_text(encoding="utf-8"))

    config = config_from_mapping(data)
    validate_config(config)
    return config


def config_from_mapping(data: dict[str, Any]) -> AppConfig:
    backend = data.get("backend", {})
    snmp = data.get("snmp", {})
    http = data.get("http", {})
    mqtt = data.get("mqtt", {})
    logging = data.get("logging", {})
    diagnostics = data.get("diagnostics", {})
    update = data.get("update", {})
    notifications = data.get("notifications", {})
    power_actions = data.get("power_actions", {})
    return AppConfig(
        backend=BackendConfig(
            type=str(backend.get("type", "apcupsd")),
            command=list(backend.get("command", ["apcaccess", "status", "localhost:3551"])),
            poll_interval_seconds=float(backend.get("poll_interval_seconds", 3)),
        ),
        snmp=SnmpConfig(
            enabled=bool(snmp.get("enabled", True)),
            listen=str(snmp.get("listen", "0.0.0.0")),
            port=int(snmp.get("port", 161)),
            community=str(snmp.get("community", "public")),
            developer_log=bool(snmp.get("developer_log", True)),
        ),
        http=HttpConfig(
            enabled=bool(http.get("enabled", True)),
            listen=str(http.get("listen", "0.0.0.0")),
            port=int(http.get("port", 8080)),
            api_enabled=bool(http.get("api_enabled", True)),
            prometheus_enabled=bool(http.get("prometheus_enabled", True)),
            homeassistant_enabled=bool(http.get("homeassistant_enabled", True)),
            auth_mode=str(http.get("auth_mode", "disabled")),
            auth_username=str(http.get("auth_username", "")),
            auth_password=str(http.get("auth_password", "")),
            auth_bypass_networks=list(
                http.get(
                    "auth_bypass_networks",
                    [
                        "127.0.0.0/8",
                        "::1/128",
                        "10.0.0.0/8",
                        "172.16.0.0/12",
                        "192.168.0.0/16",
                        "fc00::/7",
                        "fe80::/10",
                    ],
                )
            ),
        ),
        mqtt=MqttConfig(
            enabled=bool(mqtt.get("enabled", False)),
            host=str(mqtt.get("host", "localhost")),
            port=int(mqtt.get("port", 1883)),
            client_id=str(mqtt.get("client_id", "powerpi-ups-gateway")),
            topic_prefix=str(mqtt.get("topic_prefix", "powerpi/ups")),
            discovery_prefix=str(mqtt.get("discovery_prefix", "homeassistant")),
            username=str(mqtt.get("username", "")),
            password=str(mqtt.get("password", "")),
            publish_interval_seconds=float(mqtt.get("publish_interval_seconds", 30)),
        ),
        logging=LoggingConfig(
            level=str(logging.get("level", "INFO")),
            file_path=str(logging.get("file_path", "/var/log/pug/pug.log")),
            apcupsd_events_path=str(logging.get("apcupsd_events_path", "/var/log/apcupsd.events")),
            web_tail_lines=int(logging.get("web_tail_lines", 300)),
            timezone=str(logging.get("timezone", "UTC")),
        ),
        diagnostics=DiagnosticsConfig(
            before_command=list(diagnostics.get("before_command", ["systemctl", "stop", "apcupsd"])),
            after_command=list(diagnostics.get("after_command", ["systemctl", "start", "apcupsd"])),
            self_test_command=list(diagnostics.get("self_test_command", ["apctest"])),
            self_test_selection=str(diagnostics.get("self_test_selection", "2")),
            battery_calibration_command=list(diagnostics.get("battery_calibration_command", ["apctest"])),
            battery_calibration_selection=str(diagnostics.get("battery_calibration_selection", "10")),
            command_timeout_seconds=int(diagnostics.get("command_timeout_seconds", 21600)),
        ),
        update=UpdateConfig(
            gitlab_base_url=str(update.get("gitlab_base_url", "https://git.vns.ae")),
            project_path=str(update.get("project_path", "ahsan/pug")),
            check_interval=str(update.get("check_interval", "7d")),
            last_update_check=str(update.get("last_update_check", "")),
            latest_version=str(update.get("latest_version", "")),
            latest_release_url=str(update.get("latest_release_url", "")),
            latest_release_name=str(update.get("latest_release_name", "")),
        ),
        notifications=NotificationConfig(
            discord_enabled=bool(notifications.get("discord_enabled", False)),
            discord_webhook_url_file=str(notifications.get("discord_webhook_url_file", "/etc/pug/secrets/discord-webhook")),
            email_enabled=bool(notifications.get("email_enabled", False)),
            smtp_host=str(notifications.get("smtp_host", "")),
            smtp_port=int(notifications.get("smtp_port", 587)),
            smtp_security=str(notifications.get("smtp_security", "starttls")),
            smtp_username=str(notifications.get("smtp_username", "")),
            smtp_password_file=str(notifications.get("smtp_password_file", "/etc/pug/secrets/smtp-password")),
            email_from=str(notifications.get("email_from", "")),
            email_recipients=list(notifications.get("email_recipients", [])),
            minimum_severity=str(notifications.get("minimum_severity", "warning")),
            timeout_seconds=int(notifications.get("timeout_seconds", 10)),
        ),
        power_actions=PowerActionsConfig(
            enabled=bool(power_actions.get("enabled", False)),
            armed=bool(power_actions.get("armed", False)),
            dry_run=bool(power_actions.get("dry_run", True)),
            minimum_on_battery_seconds=int(power_actions.get("minimum_on_battery_seconds", 180)),
            battery_charge_percent=int(power_actions.get("battery_charge_percent", 30)),
            runtime_minutes=int(power_actions.get("runtime_minutes", 10)),
            threshold_mode=str(power_actions.get("threshold_mode", "any")),
            consecutive_samples=int(power_actions.get("consecutive_samples", 3)),
            maximum_state_age_seconds=int(power_actions.get("maximum_state_age_seconds", 15)),
            rearm_after_online_seconds=int(power_actions.get("rearm_after_online_seconds", 600)),
            emergency_enabled=bool(power_actions.get("emergency_enabled", True)),
            emergency_battery_charge_percent=int(power_actions.get("emergency_battery_charge_percent", 8)),
            emergency_runtime_minutes=int(power_actions.get("emergency_runtime_minutes", 2)),
            proceed_if_ha_preflight_failed=bool(power_actions.get("proceed_if_ha_preflight_failed", False)),
            proxmox_servers=list(power_actions.get("proxmox_servers", [])),
            verify_tls=bool(power_actions.get("verify_tls", True)),
            ca_certificate_path=str(power_actions.get("ca_certificate_path", "")),
            request_timeout_seconds=int(power_actions.get("request_timeout_seconds", 10)),
            delay_between_nodes_seconds=int(power_actions.get("delay_between_nodes_seconds", 20)),
            ha_disarm_before_shutdown=bool(power_actions.get("ha_disarm_before_shutdown", True)),
            ha_disarm_mode=str(power_actions.get("ha_disarm_mode", "freeze")),
            ha_recovery_mode=str(power_actions.get("ha_recovery_mode", "manual")),
            ha_require_all_nodes=bool(power_actions.get("ha_require_all_nodes", True)),
            ha_require_quorum=bool(power_actions.get("ha_require_quorum", True)),
            ha_require_storage_healthy=bool(power_actions.get("ha_require_storage_healthy", True)),
            ha_require_ceph_healthy=bool(power_actions.get("ha_require_ceph_healthy", True)),
            ha_health_stable_seconds=int(power_actions.get("ha_health_stable_seconds", 120)),
            rearm_only_if_pug_disarmed_ha=bool(power_actions.get("rearm_only_if_pug_disarmed_ha", True)),
            state_file_path=str(power_actions.get("state_file_path", "/var/lib/pug/power-actions.json")),
        ),
    )


def save_config(config: AppConfig, path: str | Path) -> None:
    validate_config(config)
    Path(path).write_text(render_config(config), encoding="utf-8")


def render_config(config: AppConfig) -> str:
    data = asdict(config)
    sections = []
    for section, values in data.items():
        lines = [f"{section}:"]
        for key, value in values.items():
            lines.append(f"  {key}: {_format_yaml_value(value)}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + "\n"


def validate_config(config: AppConfig) -> None:
    if config.backend.type not in {"apcupsd", "nut"}:
        raise ConfigError(f"unsupported backend type: {config.backend.type}")
    if not config.backend.command:
        raise ConfigError("backend.command must not be empty")
    if config.backend.poll_interval_seconds <= 0:
        raise ConfigError("backend.poll_interval_seconds must be greater than zero")
    if not 1 <= config.snmp.port <= 65535:
        raise ConfigError("snmp.port must be between 1 and 65535")
    if not config.snmp.community:
        raise ConfigError("snmp.community must not be empty")
    if not 1 <= config.http.port <= 65535:
        raise ConfigError("http.port must be between 1 and 65535")
    if config.http.auth_mode not in {"disabled", "always", "remote"}:
        raise ConfigError("http.auth_mode must be disabled, always, or remote")
    if config.http.auth_mode != "disabled" and (not config.http.auth_username or not config.http.auth_password):
        raise ConfigError("http.auth_username and http.auth_password are required when authentication is enabled")
    for network in config.http.auth_bypass_networks:
        try:
            ipaddress.ip_network(network, strict=False)
        except ValueError as exc:
            raise ConfigError(f"invalid http.auth_bypass_networks entry: {network}") from exc
    if not 1 <= config.mqtt.port <= 65535:
        raise ConfigError("mqtt.port must be between 1 and 65535")
    if config.mqtt.publish_interval_seconds <= 0:
        raise ConfigError("mqtt.publish_interval_seconds must be greater than zero")
    if config.logging.web_tail_lines <= 0:
        raise ConfigError("logging.web_tail_lines must be greater than zero")
    if not config.logging.timezone:
        raise ConfigError("logging.timezone must not be empty")
    if not config.diagnostics.self_test_command:
        raise ConfigError("diagnostics.self_test_command must not be empty")
    if not config.diagnostics.self_test_selection:
        raise ConfigError("diagnostics.self_test_selection must not be empty")
    if not config.diagnostics.battery_calibration_command:
        raise ConfigError("diagnostics.battery_calibration_command must not be empty")
    if not config.diagnostics.battery_calibration_selection:
        raise ConfigError("diagnostics.battery_calibration_selection must not be empty")
    if config.diagnostics.command_timeout_seconds <= 0:
        raise ConfigError("diagnostics.command_timeout_seconds must be greater than zero")
    if config.update.check_interval not in {"off", "1d", "7d"}:
        raise ConfigError("update.check_interval must be off, 1d, or 7d")
    if not config.update.gitlab_base_url:
        raise ConfigError("update.gitlab_base_url must not be empty")
    if not config.update.project_path:
        raise ConfigError("update.project_path must not be empty")
    if config.power_actions.enabled and config.http.enabled and config.http.auth_mode == "disabled":
        raise ConfigError("HTTP authentication must be enabled before power_actions can be enabled")
    if config.notifications.smtp_security not in {"none", "starttls", "tls"}:
        raise ConfigError("notifications.smtp_security must be none, starttls, or tls")
    if not 1 <= config.notifications.smtp_port <= 65535:
        raise ConfigError("notifications.smtp_port must be between 1 and 65535")
    if config.notifications.email_enabled and (not config.notifications.smtp_host or not config.notifications.email_from or not config.notifications.email_recipients):
        raise ConfigError("email notifications require smtp_host, email_from, and email_recipients")
    if config.notifications.minimum_severity not in {"info", "warning", "critical"}:
        raise ConfigError("notifications.minimum_severity must be info, warning, or critical")
    if config.notifications.timeout_seconds <= 0:
        raise ConfigError("notifications.timeout_seconds must be greater than zero")
    if config.notifications.discord_enabled and not config.notifications.discord_webhook_url_file:
        raise ConfigError("notifications.discord_webhook_url_file is required when Discord is enabled")
    if config.power_actions.threshold_mode not in {"any", "all"}:
        raise ConfigError("power_actions.threshold_mode must be any or all")
    if config.power_actions.ha_disarm_mode not in {"freeze", "ignore"}:
        raise ConfigError("power_actions.ha_disarm_mode must be freeze or ignore")
    if config.power_actions.ha_recovery_mode not in {"manual", "automatic_safe", "leave_disarmed"}:
        raise ConfigError("power_actions.ha_recovery_mode must be manual, automatic_safe, or leave_disarmed")
    if config.power_actions.armed and not config.power_actions.enabled:
        raise ConfigError("power_actions must be enabled before they can be armed")
    if config.power_actions.enabled and not config.power_actions.proxmox_servers:
        raise ConfigError("power_actions.proxmox_servers must not be empty when enabled")
    if not 0 <= config.power_actions.battery_charge_percent <= 100 or not 0 <= config.power_actions.emergency_battery_charge_percent <= 100:
        raise ConfigError("power action battery thresholds must be between 0 and 100")
    if config.power_actions.runtime_minutes < 0 or config.power_actions.emergency_runtime_minutes < 0 or config.power_actions.delay_between_nodes_seconds < 0:
        raise ConfigError("power action runtime thresholds and node delay must not be negative")
    for name, value in {
        "minimum_on_battery_seconds": config.power_actions.minimum_on_battery_seconds,
        "consecutive_samples": config.power_actions.consecutive_samples,
        "maximum_state_age_seconds": config.power_actions.maximum_state_age_seconds,
        "rearm_after_online_seconds": config.power_actions.rearm_after_online_seconds,
        "request_timeout_seconds": config.power_actions.request_timeout_seconds,
        "ha_health_stable_seconds": config.power_actions.ha_health_stable_seconds,
    }.items():
        if value <= 0:
            raise ConfigError(f"power_actions.{name} must be greater than zero")
    for server in config.power_actions.proxmox_servers:
        parts = str(server).split("|")
        if len(parts) != 6 or not all(part.strip() for part in parts):
            raise ConfigError("each power_actions.proxmox_servers entry must be name|host|node|token_id|token_secret_file|order")
        try:
            int(parts[-1])
        except ValueError as exc:
            raise ConfigError("Proxmox server shutdown order must be an integer") from exc


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current: dict[str, Any] | None = None

    for original in text.splitlines():
        line = original.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            key = line[:-1].strip()
            current = {}
            result[key] = current
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        current[key.strip()] = _parse_scalar(value.strip())

    return result


def _parse_scalar(value: str) -> Any:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def parse_command(value: str) -> list[str]:
    return shlex.split(value)


def format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


def _format_yaml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_format_yaml_value(item) for item in value) + "]"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
