from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pug.raw_stats import raw_stats
from pug.state import UPSState


@dataclass(frozen=True)
class SensorSpec:
    object_id: str
    name: str
    state_key: str
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"
    entity_category: str | None = None
    icon: str | None = None


NORMALIZED_SENSORS = [
    SensorSpec("battery_charge", "Battery Charge", "battery_charge_percent", "%", "battery"),
    SensorSpec("runtime", "Runtime", "runtime_minutes", "min", "duration"),
    SensorSpec("seconds_on_battery", "Seconds On Battery", "seconds_on_battery", "s", "duration"),
    SensorSpec("battery_voltage", "Battery Voltage", "battery_voltage", "V", "voltage"),
    SensorSpec("input_voltage", "Input Voltage", "input_voltage", "V", "voltage"),
    SensorSpec("output_voltage", "Output Voltage", "output_voltage", "V", "voltage"),
    SensorSpec("output_current", "Output Current", "output_current", "A", "current"),
    SensorSpec("line_frequency", "Line Frequency", "line_frequency", "Hz", "frequency"),
    SensorSpec("load", "Load", "load_percent", "%"),
    SensorSpec("load_va", "Load VA", "load_va_percent", "%"),
    SensorSpec("temperature", "Temperature", "internal_temperature_c", "\u00b0C", "temperature"),
    SensorSpec("nominal_output_voltage", "Nominal Output Voltage", "nominal_output_voltage", "V", "voltage", entity_category="diagnostic"),
    SensorSpec("nominal_power", "Nominal Power", "nominal_power_watts", "W", "power", entity_category="diagnostic"),
    SensorSpec("nominal_va", "Nominal Apparent Power", "nominal_va", "VA", "apparent_power", entity_category="diagnostic"),
    SensorSpec("min_battery_charge", "Minimum Battery Charge", "min_battery_charge_percent", "%", "battery", entity_category="diagnostic"),
    SensorSpec("min_runtime", "Minimum Runtime", "min_runtime_minutes", "min", "duration", entity_category="diagnostic"),
]

RAW_SENSOR_SPECS = {
    "BCHARGE": SensorSpec("bcharge", "Battery Charge", "BCHARGE", "%", "battery"),
    "LOADPCT": SensorSpec("loadpct", "Load", "LOADPCT", "%"),
    "LOADAPNT": SensorSpec("loadapnt", "Load VA", "LOADAPNT", "%"),
    "TIMELEFT": SensorSpec("timeleft", "Runtime", "TIMELEFT", "min", "duration"),
    "MBATTCHG": SensorSpec("mbattchg", "Minimum Battery Charge", "MBATTCHG", "%", "battery", entity_category="diagnostic"),
    "MINTIMEL": SensorSpec("mintimel", "Minimum Runtime", "MINTIMEL", "min", "duration", entity_category="diagnostic"),
    "MAXTIME": SensorSpec("maxtime", "Maximum Runtime", "MAXTIME", "s", "duration", entity_category="diagnostic"),
    "LINEV": SensorSpec("linev", "Input Voltage", "LINEV", "V", "voltage"),
    "OUTPUTV": SensorSpec("outputv", "Output Voltage", "OUTPUTV", "V", "voltage"),
    "BATTV": SensorSpec("battv", "Battery Voltage", "BATTV", "V", "voltage"),
    "NOMOUTV": SensorSpec("nomoutv", "Nominal Output Voltage", "NOMOUTV", "V", "voltage", entity_category="diagnostic"),
    "OUTCURNT": SensorSpec("outcurnt", "Output Current", "OUTCURNT", "A", "current"),
    "LINEFREQ": SensorSpec("linefreq", "Line Frequency", "LINEFREQ", "Hz", "frequency"),
    "ITEMP": SensorSpec("itemp", "Internal Temperature", "ITEMP", "\u00b0C", "temperature"),
    "TONBATT": SensorSpec("tonbatt", "Seconds On Battery", "TONBATT", "s", "duration"),
    "CUMONBATT": SensorSpec("cumonbatt", "Cumulative Time On Battery", "CUMONBATT", "s", "duration", entity_category="diagnostic"),
    "DWAKE": SensorSpec("dwake", "Wake Delay", "DWAKE", "s", "duration", entity_category="diagnostic"),
    "DSHUTD": SensorSpec("dshutd", "Shutdown Delay", "DSHUTD", "s", "duration", entity_category="diagnostic"),
    "NUMXFERS": SensorSpec("numxfers", "Transfer Count", "NUMXFERS", None, None, entity_category="diagnostic"),
    "NOMPOWER": SensorSpec("nompower", "Nominal Power", "NOMPOWER", "W", "power", entity_category="diagnostic"),
    "NOMAPNT": SensorSpec("nomapnt", "Nominal Apparent Power", "NOMAPNT", "VA", "apparent_power", entity_category="diagnostic"),
}


def discovery_payloads(state: UPSState, state_topic: str, discovery_prefix: str = "homeassistant") -> dict[str, Any]:
    device = {
        "identifiers": ["powerpi-ups-gateway"],
        "name": state.name,
        "manufacturer": state.manufacturer,
        "model": state.model,
    }
    payloads: dict[str, Any] = {}
    payloads[f"{discovery_prefix}/sensor/powerpi_ups/status/config"] = {
        "name": "UPS Status",
        "unique_id": "powerpi_ups_status",
        "state_topic": f"{state_topic}/status",
        "icon": "mdi:power-plug",
        "device": device,
    }
    binary_sensors = {
        "online": ("UPS Online", f"{state_topic}/online", "connectivity"),
        "on_battery": ("UPS On Battery", f"{state_topic}/on_battery", "problem"),
        "replace_battery": ("UPS Replace Battery", f"{state_topic}/replace_battery", "problem"),
    }
    for object_id, (name, topic, device_class) in binary_sensors.items():
        payloads[f"{discovery_prefix}/binary_sensor/powerpi_ups/{object_id}/config"] = {
            "name": name,
            "unique_id": f"powerpi_ups_{object_id}",
            "state_topic": topic,
            "payload_on": "ON",
            "payload_off": "OFF",
            "device_class": device_class,
            "device": device,
        }
    for spec in NORMALIZED_SENSORS:
        payloads[f"{discovery_prefix}/sensor/powerpi_ups/{spec.object_id}/config"] = _sensor_payload(
            name=f"UPS {spec.name}",
            unique_id=f"powerpi_ups_{spec.object_id}",
            state_topic=f"{state_topic}/{spec.state_key}",
            device=device,
            spec=spec,
        )
    for stat in raw_stats(state):
        topic = f"{discovery_prefix}/sensor/powerpi_ups_raw/{stat.slug}/config"
        spec = RAW_SENSOR_SPECS.get(stat.key.upper())
        if spec and stat.number is not None:
            payloads[topic] = _raw_sensor_payload(
                name=f"UPS Raw {spec.name}",
                unique_id=f"powerpi_ups_raw_{stat.slug}",
                state_topic=f"{state_topic}/raw/{stat.slug}",
                device=device,
                spec=spec,
                value_template="{{ value | regex_findall_index('[-+]?[0-9]*\\.?[0-9]+') | float }}",
            )
        else:
            payloads[topic] = {
                "name": f"UPS Raw {stat.key}",
                "unique_id": f"powerpi_ups_raw_{stat.slug}",
                "state_topic": f"{state_topic}/raw/{stat.slug}",
                "device": device,
                "entity_category": "diagnostic",
            }
    return payloads


def _raw_sensor_payload(
    name: str,
    unique_id: str,
    state_topic: str,
    device: dict[str, Any],
    spec: SensorSpec,
    value_template: str | None = None,
) -> dict[str, Any]:
    payload = _sensor_payload(name, unique_id, state_topic, device, spec, value_template)
    payload["entity_category"] = "diagnostic"
    return payload


def _sensor_payload(
    name: str,
    unique_id: str,
    state_topic: str,
    device: dict[str, Any],
    spec: SensorSpec,
    value_template: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "unique_id": unique_id,
        "state_topic": state_topic,
        "device": device,
    }
    if spec.unit:
        payload["unit_of_measurement"] = spec.unit
    if spec.device_class:
        payload["device_class"] = spec.device_class
    if spec.state_class:
        payload["state_class"] = spec.state_class
    if spec.entity_category:
        payload["entity_category"] = spec.entity_category
    if spec.icon:
        payload["icon"] = spec.icon
    if value_template:
        payload["value_template"] = value_template
    return payload
