from __future__ import annotations

from typing import Any

from pug.raw_stats import raw_stats
from pug.state import UPSState


def discovery_payloads(state: UPSState, state_topic: str, discovery_prefix: str = "homeassistant") -> dict[str, Any]:
    device = {
        "identifiers": ["powerpi-ups-gateway"],
        "name": state.name,
        "manufacturer": state.manufacturer,
        "model": state.model,
    }
    sensors = {
        "battery_charge": ("Battery Charge", "%", "battery", "{{ value_json.battery_charge_percent }}"),
        "runtime": ("Runtime", "min", "duration", "{{ value_json.runtime_minutes }}"),
        "load": ("Load", "%", "power", "{{ value_json.load_percent }}"),
        "input_voltage": ("Input Voltage", "V", "voltage", "{{ value_json.input_voltage }}"),
        "output_voltage": ("Output Voltage", "V", "voltage", "{{ value_json.output_voltage }}"),
        "temperature": ("Temperature", "C", "temperature", "{{ value_json.internal_temperature_c }}"),
    }
    payloads: dict[str, Any] = {}
    for object_id, (name, unit, device_class, template) in sensors.items():
        topic = f"{discovery_prefix}/sensor/powerpi_ups/{object_id}/config"
        payloads[topic] = {
            "name": f"UPS {name}",
            "unique_id": f"powerpi_ups_{object_id}",
            "state_topic": state_topic,
            "unit_of_measurement": unit,
            "device_class": device_class,
            "value_template": template,
            "device": device,
        }
    for stat in raw_stats(state):
        topic = f"{discovery_prefix}/sensor/powerpi_ups_raw/{stat.slug}/config"
        payload: dict[str, Any] = {
            "name": f"UPS Raw {stat.key}",
            "unique_id": f"powerpi_ups_raw_{stat.slug}",
            "state_topic": f"{state_topic}/raw/{stat.slug}",
            "device": device,
        }
        if stat.number is not None:
            payload["value_template"] = "{{ value }}"
        payloads[topic] = payload
    return payloads
