from pug.collector.simulator import simulator_state
from pug.config import AppConfig, load_config, save_config
from pug.frontends.homeassistant import discovery_payloads
from pug.frontends.http import config_from_form, render_control_page
from pug.frontends.prometheus import render_metrics


def test_prometheus_metrics_include_core_values() -> None:
    metrics = render_metrics(simulator_state())

    assert "powerpi_ups_battery_charge_percent" in metrics
    assert "powerpi_ups_online" in metrics
    assert " 100" in metrics


def test_homeassistant_discovery_payloads_include_battery_sensor() -> None:
    payloads = discovery_payloads(simulator_state(), "powerpi/ups")

    topic = "homeassistant/sensor/powerpi_ups/battery_charge/config"
    assert topic in payloads
    assert payloads[topic]["state_topic"] == "powerpi/ups"


def test_status_page_escapes_html() -> None:
    state = simulator_state().updated(name="<UPS>").to_dict()
    page = render_control_page(state, AppConfig())

    assert "&lt;UPS&gt;" in page
    assert "<UPS>" not in page


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
