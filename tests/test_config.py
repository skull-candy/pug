import pytest

from pug.config import AppConfig, BackendConfig, ConfigError, HttpConfig, SnmpConfig, load_config, validate_config


def test_load_config_reads_project_example() -> None:
    config = load_config("config/config.example.yaml")

    assert config.backend.type == "apcupsd"
    assert config.backend.command == ["apcaccess", "status", "localhost:3551"]
    assert config.snmp.port == 161
    assert config.snmp.developer_log is True
    assert config.http.port == 8080
    assert config.http.auth_mode == "disabled"
    assert "192.168.0.0/16" in config.http.auth_bypass_networks
    assert config.mqtt.enabled is False
    assert config.logging.apcupsd_events_path == "/var/log/apcupsd.events"
    assert config.logging.timezone == "UTC"
    assert config.diagnostics.before_command == ["systemctl", "stop", "apcupsd"]
    assert config.diagnostics.after_command == ["systemctl", "start", "apcupsd"]
    assert config.diagnostics.self_test_command == ["apctest"]
    assert config.diagnostics.self_test_selection == "2"
    assert config.diagnostics.battery_calibration_selection == "10"
    assert config.update.gitlab_base_url == "https://git.vns.ae"
    assert config.update.project_path == "ahsan/pug"
    assert config.update.check_interval == "7d"


def test_config_rejects_invalid_snmp_port() -> None:
    config = AppConfig(snmp=SnmpConfig(port=70000))

    with pytest.raises(ConfigError, match="snmp.port"):
        validate_config(config)


def test_config_rejects_empty_backend_command() -> None:
    config = AppConfig(backend=BackendConfig(command=[]))

    with pytest.raises(ConfigError, match="backend.command"):
        validate_config(config)


def test_config_rejects_auth_without_credentials() -> None:
    config = AppConfig(http=HttpConfig(auth_mode="remote", auth_username="admin", auth_password=""))

    with pytest.raises(ConfigError, match="auth_username"):
        validate_config(config)


def test_config_rejects_invalid_auth_bypass_network() -> None:
    config = AppConfig(
        http=HttpConfig(
            auth_mode="remote",
            auth_username="admin",
            auth_password="secret",
            auth_bypass_networks=["not-a-network"],
        )
    )

    with pytest.raises(ConfigError, match="auth_bypass_networks"):
        validate_config(config)


def test_config_preserves_hash_inside_quoted_value(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """mqtt:
  password: "abc#123"
""",
        encoding="utf-8",
    )

    assert load_config(path).mqtt.password == "abc#123"
