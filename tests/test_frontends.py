from pug.collector.simulator import simulator_state
from pug.config import AppConfig, LoggingConfig, load_config, save_config
from pug.diagnostics import DiagnosticSnapshot
from pug.frontends.homeassistant import discovery_payloads
from pug.frontends.http import (
    config_from_form,
    display_label,
    display_value,
    power_flow_mode,
    raw_display_label,
    read_ups_icon,
    render_control_page,
    render_diagnostics_page,
    render_logs_page,
    render_raw_stats_page,
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

    assert next(iter(payloads)) == "homeassistant/sensor/powerpi_ups/status/config"
    topic = "homeassistant/sensor/powerpi_ups/battery_charge/config"
    assert topic in payloads
    assert payloads[topic]["state_topic"] == "powerpi/ups/battery_charge_percent"
    assert payloads[topic]["device_class"] == "battery"
    assert payloads[topic]["state_class"] == "measurement"
    assert payloads["homeassistant/sensor/powerpi_ups/status/config"]["state_topic"] == "powerpi/ups/status"
    assert payloads["homeassistant/binary_sensor/powerpi_ups/online/config"]["state_topic"] == "powerpi/ups/online"
    assert payloads["homeassistant/binary_sensor/powerpi_ups/online/config"]["device_class"] == "connectivity"
    assert payloads["homeassistant/binary_sensor/powerpi_ups/replace_battery/config"]["device_class"] == "problem"
    assert payloads["homeassistant/sensor/powerpi_ups/temperature/config"]["state_topic"] == "powerpi/ups/internal_temperature_c"
    assert payloads["homeassistant/sensor/powerpi_ups/temperature/config"]["unit_of_measurement"] == "°C"


def test_homeassistant_discovery_payloads_include_raw_sensors() -> None:
    payloads = discovery_payloads(simulator_state().updated(raw={"SELFTEST": "NG"}), "powerpi/ups")

    topic = "homeassistant/sensor/powerpi_ups_raw/selftest/config"
    assert topic in payloads
    assert payloads[topic]["state_topic"] == "powerpi/ups/raw/selftest"
    assert payloads[topic]["entity_category"] == "diagnostic"


def test_homeassistant_discovery_payloads_type_all_normalized_sensors() -> None:
    payloads = discovery_payloads(simulator_state(), "powerpi/ups")

    assert payloads["homeassistant/sensor/powerpi_ups/output_current/config"]["device_class"] == "current"
    assert payloads["homeassistant/sensor/powerpi_ups/output_current/config"]["unit_of_measurement"] == "A"
    assert payloads["homeassistant/sensor/powerpi_ups/line_frequency/config"]["device_class"] == "frequency"
    assert payloads["homeassistant/sensor/powerpi_ups/line_frequency/config"]["unit_of_measurement"] == "Hz"
    assert payloads["homeassistant/sensor/powerpi_ups/load/config"]["unit_of_measurement"] == "%"
    assert "device_class" not in payloads["homeassistant/sensor/powerpi_ups/load/config"]
    assert payloads["homeassistant/sensor/powerpi_ups/load_va/config"]["unit_of_measurement"] == "%"
    assert payloads["homeassistant/sensor/powerpi_ups/battery_voltage/config"]["device_class"] == "voltage"
    assert payloads["homeassistant/sensor/powerpi_ups/nominal_power/config"]["device_class"] == "power"
    assert payloads["homeassistant/sensor/powerpi_ups/nominal_power/config"]["entity_category"] == "diagnostic"


def test_homeassistant_discovery_payloads_type_apcupsd_raw_sensors() -> None:
    payloads = discovery_payloads(
        simulator_state().updated(raw={"LINEV": "221.7 Volts", "OUTCURNT": "3.84 Amps", "LINEFREQ": "50.0 Hz"}),
        "powerpi/ups",
    )

    linev = payloads["homeassistant/sensor/powerpi_ups_raw/linev/config"]
    current = payloads["homeassistant/sensor/powerpi_ups_raw/outcurnt/config"]
    frequency = payloads["homeassistant/sensor/powerpi_ups_raw/linefreq/config"]
    assert linev["device_class"] == "voltage"
    assert linev["unit_of_measurement"] == "V"
    assert linev["entity_category"] == "diagnostic"
    assert current["device_class"] == "current"
    assert current["unit_of_measurement"] == "A"
    assert current["entity_category"] == "diagnostic"
    assert frequency["device_class"] == "frequency"
    assert frequency["unit_of_measurement"] == "Hz"
    assert frequency["entity_category"] == "diagnostic"
    assert linev["value_template"] == "{{ value | regex_findall_index('[-+]?[0-9]*\\.?[0-9]+') | float }}"


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
    assert "Line / AVR path active" in page
    assert "Line / AVR" in page
    assert "Bypass Path" in page
    assert "Inactive / standby path" in page
    assert 'class="power desktop"' in page
    assert 'class="power mobile"' in page
    assert "Input Voltage" in page
    assert "Output Voltage" in page
    assert "Self Test" not in page
    assert "/assets/ups-icons/input.png" in page
    assert "/assets/ups-icons/avr.png" in page
    assert "/assets/ups-icons/inverter.png" in page
    assert "Rectifier" not in page
    assert "UPS Details" in page
    assert 'href="/raw"' in page
    assert "<h2>Raw Backend Stats</h2>" not in page
    assert 'href="/settings"' in page
    assert 'action="/config"' not in page


def test_ups_icon_assets_are_packaged() -> None:
    icon = read_ups_icon("input.png")

    assert icon is not None
    assert icon.startswith(b"\x89PNG\r\n\x1a\n")
    assert read_ups_icon("../input.png") is None


def test_raw_stats_page_contains_backend_values() -> None:
    page = render_raw_stats_page(simulator_state().updated(raw={"LINEV": "221.7 Volts"}).to_dict(), AppConfig())

    assert "Raw Backend Stats" in page
    assert 'href="/api/raw"' in page
    assert "Input Voltage" in page
    assert "221.7 Volts" in page
    assert 'class="active" href="/raw"' in page


def test_settings_page_contains_configuration_form() -> None:
    page = render_settings_page(AppConfig())

    assert "Settings" in page
    assert 'action="/config"' in page
    assert "Log file path" in page
    assert "apcupsd events path" in page
    assert "Self test command" in page


def test_logs_page_renders_bounded_tail(tmp_path) -> None:
    log_path = tmp_path / "pug.log"
    events_path = tmp_path / "apcupsd.events"
    log_path.write_text("".join(f"line {index}\n" for index in range(20)), encoding="utf-8")
    events_path.write_text("".join(f"event {index}\n" for index in range(10)), encoding="utf-8")
    config = AppConfig(logging=LoggingConfig(file_path=str(log_path), apcupsd_events_path=str(events_path), web_tail_lines=5))
    lines = tail_log_lines(str(log_path), 5)
    event_lines = tail_log_lines(str(events_path), 5)
    page = render_logs_page(config, lines, event_lines)

    assert lines == [f"line {index}" for index in range(15, 20)]
    assert event_lines == [f"event {index}" for index in range(5, 10)]
    assert "line 19" in page
    assert "event 9" in page
    assert "apcupsd Events" in page
    assert "line 1\n" not in page


def test_diagnostics_page_shows_actions_live_status_and_result() -> None:
    state = simulator_state().updated(raw={"SELFTEST": "PASSED"}).to_dict()
    snapshot = DiagnosticSnapshot(status="completed", action="self_test", return_code=0, output=["TEST PASSED"])

    page = render_diagnostics_page(state, AppConfig(), snapshot)

    assert "Diagnostics" in page
    assert 'name="action" value="self_test"' in page
    assert 'name="action" value="battery_calibration"' in page
    assert "Self Test Result" in page
    assert "PASSED" in page
    assert "TEST PASSED" in page


def test_display_helpers_are_human_friendly() -> None:
    assert display_label("runtime_minutes") == "Runtime Remaining"
    assert display_value("runtime_minutes", 39) == "39 min"
    assert display_value("online", True) == "Yes"
    assert raw_display_label("LASTXFER") == "Last Transfer Reason"


def test_power_flow_mode_reflects_ups_state() -> None:
    line_state = simulator_state().updated(online=True, on_battery=False, input_voltage=221.7, output_voltage=221.7).to_dict()
    battery_state = simulator_state().updated(online=False, on_battery=True).to_dict()
    bypass_state = simulator_state().updated(status_text="BYPASS", raw={"STATUS": "BYPASS"}).to_dict()
    conversion_state = simulator_state().updated(online=True, input_voltage=210.0, output_voltage=230.0).to_dict()

    assert power_flow_mode(line_state) == "line"
    assert power_flow_mode(battery_state) == "battery"
    assert power_flow_mode(bypass_state) == "bypass"
    assert power_flow_mode(conversion_state) == "online_conversion"


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
            "logging_apcupsd_events_path": ["/var/log/apcupsd.events"],
            "logging_web_tail_lines": ["300"],
            "diagnostics_self_test_command": ["apctest"],
            "diagnostics_self_test_selection": ["2"],
            "diagnostics_battery_calibration_command": ["apctest"],
            "diagnostics_battery_calibration_selection": ["10"],
            "diagnostics_command_timeout_seconds": ["21600"],
        }
    )

    assert config.snmp.enabled is False
    assert config.http.api_enabled is True
    assert config.http.prometheus_enabled is False
    assert config.http.homeassistant_enabled is False
    assert config.mqtt.enabled is False
    assert config.diagnostics.self_test_selection == "2"


def test_config_save_round_trip(tmp_path) -> None:
    path = tmp_path / "config.yaml"
    config = AppConfig()

    save_config(config, path)
    loaded = load_config(path)

    assert loaded.backend.command == ["apcaccess", "status", "localhost:3551"]
    assert loaded.http.api_enabled is True
