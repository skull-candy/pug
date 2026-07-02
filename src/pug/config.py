from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    web_tail_lines: int = 300


@dataclass(frozen=True)
class AppConfig:
    backend: BackendConfig = field(default_factory=BackendConfig)
    snmp: SnmpConfig = field(default_factory=SnmpConfig)
    http: HttpConfig = field(default_factory=HttpConfig)
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


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
            web_tail_lines=int(logging.get("web_tail_lines", 300)),
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
    if not 1 <= config.mqtt.port <= 65535:
        raise ConfigError("mqtt.port must be between 1 and 65535")
    if config.mqtt.publish_interval_seconds <= 0:
        raise ConfigError("mqtt.publish_interval_seconds must be greater than zero")
    if config.logging.web_tail_lines <= 0:
        raise ConfigError("logging.web_tail_lines must be greater than zero")


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
