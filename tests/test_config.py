import pytest

from pug.config import AppConfig, BackendConfig, ConfigError, SnmpConfig, load_config, validate_config


def test_load_config_reads_project_example() -> None:
    config = load_config("config/config.yaml")

    assert config.backend.type == "apcupsd"
    assert config.backend.command == ["apcaccess", "status", "localhost:3551"]
    assert config.snmp.port == 161
    assert config.snmp.developer_log is True


def test_config_rejects_invalid_snmp_port() -> None:
    config = AppConfig(snmp=SnmpConfig(port=70000))

    with pytest.raises(ConfigError, match="snmp.port"):
        validate_config(config)


def test_config_rejects_empty_backend_command() -> None:
    config = AppConfig(backend=BackendConfig(command=[]))

    with pytest.raises(ConfigError, match="backend.command"):
        validate_config(config)
