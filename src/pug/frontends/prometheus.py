from __future__ import annotations

from pug.raw_stats import raw_stats
from pug.state import UPSState


def render_metrics(state: UPSState) -> str:
    labels = f'source_backend="{_label(state.source_backend)}",model="{_label(state.model)}"'
    metrics = {
        "battery_charge_percent": state.battery_charge_percent,
        "runtime_minutes": state.runtime_minutes,
        "seconds_on_battery": state.seconds_on_battery,
        "battery_voltage": state.battery_voltage,
        "input_voltage": state.input_voltage,
        "output_voltage": state.output_voltage,
        "output_current": state.output_current,
        "line_frequency": state.line_frequency,
        "load_percent": state.load_percent,
        "internal_temperature_celsius": state.internal_temperature_c,
        "online": 1 if state.online else 0,
        "on_battery": 1 if state.on_battery else 0,
        "replace_battery": 1 if state.replace_battery else 0,
    }
    lines = []
    for name, value in metrics.items():
        lines.append(f"# TYPE powerpi_ups_{name} gauge")
        lines.append(f"powerpi_ups_{name}{{{labels}}} {value}")
    lines.append("# TYPE powerpi_ups_status_info gauge")
    lines.append(f'powerpi_ups_status_info{{{labels},status="{_label(state.status_text)}"}} 1')
    lines.append("# TYPE powerpi_ups_raw_numeric gauge")
    lines.append("# TYPE powerpi_ups_raw_info gauge")
    for stat in raw_stats(state):
        key = _label(stat.key)
        raw_value = _label(stat.value)
        if stat.number is not None:
            lines.append(f'powerpi_ups_raw_numeric{{{labels},key="{key}"}} {stat.number}')
        lines.append(f'powerpi_ups_raw_info{{{labels},key="{key}",value="{raw_value}"}} 1')
    return "\n".join(lines) + "\n"


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
