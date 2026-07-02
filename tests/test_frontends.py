from pug.collector.simulator import simulator_state
from pug.config import AppConfig, LoggingConfig, load_config, save_config
from pug.frontends.homeassistant import discovery_payloads
from pug.frontends.http import (
    config_from_form,
    display_label,
    display_value,
    raw_display_label,
    render_control_page,
    render_logs_page,
    render_settings_page,
    tail_log_lines,
)
from pug.frontends.prometheus import render_metrics


def test_prometheus_metrics_include_core_values() -> None:
    metrics = render_metrics(simulator_state())

    assert "powerpi_ups_battery_charge_percent" in metrics
    assert "powerpi_ups_online" in metrics
    assert 'powerpi_ups_status_info{source_backend="simulator",model="Smart-UPS 3000",status="ONLINE"} 1' in metrics
    assert " 100" in metrics


def test_prometheus_metrics_include_raw_values() -> None:
    metrics = render_metrics(simulator_state().updated(raw={"LINEV": "221.7 Volts", "SELFTEST": "NG"}))

    assert 'powerpi_ups_raw_numeric{source_backend="simulator",model="Smart-UPS 3000",key="LINEV"} 221.7' in metrics
    assert 'powerpi_ups_raw_info{source_backend="simulator",model="Smart-UPS 3000",key="SELFTEST",value="NG"} 1' in metrics


def test_homeassistant_discovery_payloads_include_battery_sensor() -> None:
    payloads = discovery_payloads(simulator_state(), "powerpi/ups")

    topic = "homeassistant/sensor/powerpi_ups/battery_charge/config"
    assert topic in payloads
    assert payloads[topic]["state_topic"] == "powerpi/ups"
    assert payloads["homeassistant/sensor/powerpi_ups/status/config"]["state_topic"] == "powerpi/ups/status"
    assert payloads["homeassistant/binary_sensor/powerpi_ups/online/config"]["state_topic"] == "powerpi/ups/online"


def test_homeassistant_discovery_payloads_include_raw_sensors() -> None:
    payloads = discovery_payloads(simulator_state().updated(raw={"SELFTEST": "NG"}), "powerpi/ups")

    topic = "homeassistant/sensor/powerpi_ups_raw/selftest/config"
    assert topic in payloads
    assert payloads[topic]["state_topic"] == "powerpi/ups/raw/selftest"


def test_status_page_escapes_html() -> None:
    state = simulator_state().updated(name="<UPS>").to_dict()
    page = render_control_page(state, AppConfig())

    assert "&lt;UPS&gt;" in page
    assert "<UPS>" not in page


def test_web_ui_uses_human_friendly_status_labels() -> None:
    state = simulator_state().to_dict()
    page = render_control_page(state, AppConfig())

    assert "Battery Charge" in page
    assert "100%" in page
    assert "Replace Battery" in page
    assert "No" in page
    assert "battery_charge_percent" not in page


def test_dashboard_has_modern_sections_and_no_settings_form() -> None:
    page = render_control_page(simulator_state().to_dict(), AppConfig())

    assert "UPS power flow diagram" in page
    assert "UPS Details" in page
    assert "Raw Backend Stats" in page
    assert 'href="/settings"' in page
    assert 'action="/config"' not in page


def test_settings_page_contains_configuration_form() -> None:
    page = render_settings_page(AppConfig())

    assert "Settings" in page
    assert 'action="/config"' in page
    assert "Log file path" in page


def test_logs_page_renders_bounded_tail(tmp_path) -> None:
    log_path = tmp_path / "pug.log"
    log_path.write_text("".join(f"line {index}\n" for index in range(20)), encoding="utf-8")
    config = AppConfig(logging=LoggingConfig(file_path=str(log_path), web_tail_lines=5))
    lines = tail_log_lines(str(log_path), 5)
    page = render_logs_page(config, lines)

    assert lines == [f"line {index}" for index in range(15, 20)]
    assert "line 19" in page
    assert "line 1\n" not in page


def test_display_helpers_are_human_friendly() -> None:
    assert display_label("runtime_minutes") == "Runtime Remaining"
    assert display_value("runtime_minutes", 39) == "39 min"
    assert display_value("online", True) == "Yes"
    assert raw_display_label("LASTXFER") == "Last Transfer Reason"


def test_config_form_can_disable_methods() -> None:
    config = config_from_form(
        {
            "backend_type": ["apcupsd"],
            "backend_command": ["apcaccess status localhost:3551"],
            "backend_poll_interval_seconds": ["5"],
            "snmp_listen": ["0.0.0.0"],
            "snmp_port": ["1161"],
            "snmp_community": ["public"],
            "http_api_enabled": ["on"],
            "http_listen": ["0.0.0.0"],
            "http_port": ["8080"],
            "mqtt_host": ["mqtt.local"],
            "mqtt_port": ["1883"],
            "mqtt_client_id": ["pug"],
            "mqtt_topic_prefix": ["powerpi/ups"],
            "mqtt_discovery_prefix": ["homeassistant"],
            "mqtt_publish_interval_seconds": ["30"],
            "logging_level": ["INFO"],
            "logging_file_path": ["/var/log/pug/pug.log"],
            "logging_web_tail_lines": ["300"],
        }
    )

    assert config.snmp.enabled is False
    assert config.http.api_enabled is True
    assert config.http.prometheus_enabled is False
    assert config.http.homeassistant_enabled is False
    assert config.mqtt.enabled is False


def test_config_save_round_trip(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    config = AppConfig()

    save_config(config, path)
    loaded = load_config(path)

    assert loaded.backend.command == ["apcaccess", "status", "localhost:3551"]
    assert loaded.http.api_enabled is True
