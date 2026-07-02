from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
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
class LoggingConfig:
    level: str = "INFO"


@dataclass(frozen=True)
class AppConfig:
    backend: BackendConfig = field(default_factory=BackendConfig)
    snmp: SnmpConfig = field(default_factory=SnmpConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(path: str | Path | None) -> AppConfig:
    data: dict[str, Any] = {}
    if path:
        config_path = Path(path)
        if config_path.exists():
            data = _parse_simple_yaml(config_path.read_text(encoding="utf-8"))

    backend = data.get("backend", {})
    snmp = data.get("snmp", {})
    logging = data.get("logging", {})
    config = AppConfig(
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
        logging=LoggingConfig(level=str(logging.get("level", "INFO"))),
    )
    validate_config(config)
    return config


def validate_config(config: AppConfig) -> None:
    if config.backend.type not in {"apcupsd"}:
        raise ConfigError(f"unsupported backend type: {config.backend.type}")
    if not config.backend.command:
        raise ConfigError("backend.command must not be empty")
    if config.backend.poll_interval_seconds <= 0:
        raise ConfigError("backend.poll_interval_seconds must be greater than zero")
    if not 1 <= config.snmp.port <= 65535:
        raise ConfigError("snmp.port must be between 1 and 65535")
    if not config.snmp.community:
        raise ConfigError("snmp.community must not be empty")


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current: dict[str, Any] | None = None

    for original in text.splitlines():
        line = original.split("#", 1)[0].rstrip()
        if not line.strip():
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
