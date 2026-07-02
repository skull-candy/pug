from __future__ import annotations

import subprocess
from collections.abc import Sequence

from pug.collector.base import Collector
from pug.state import UPSState


class NutCollector(Collector):
    def __init__(self, command: Sequence[str]) -> None:
        self.command = list(command)

    def collect(self) -> UPSState:
        result = subprocess.run(
            self.command,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return parse_nut_status(result.stdout)


def parse_nut_status(text: str) -> UPSState:
    raw = _parse_lines(text)
    status_tokens = set(raw.get("ups.status", "").upper().split())
    return UPSState(
        manufacturer=raw.get("device.mfr", raw.get("ups.mfr", "UPS")),
        model=raw.get("device.model", raw.get("ups.model", "Unknown UPS")),
        name=raw.get("ups.id", raw.get("device.model", "PowerPi UPS")),
        serial=raw.get("device.serial", raw.get("ups.serial", "")),
        firmware=raw.get("ups.firmware", ""),
        battery_date=raw.get("battery.date", ""),
        status_text=raw.get("ups.status", "UNKNOWN"),
        online="OL" in status_tokens,
        on_battery="OB" in status_tokens,
        replace_battery="RB" in status_tokens,
        battery_charge_percent=_int_value(raw.get("battery.charge")),
        runtime_minutes=round(_float_value(raw.get("battery.runtime")) / 60),
        seconds_on_battery=_int_value(raw.get("ups.timer.start")),
        battery_voltage=_float_value(raw.get("battery.voltage")),
        input_voltage=_float_value(raw.get("input.voltage")),
        output_voltage=_float_value(raw.get("output.voltage")),
        output_current=_float_value(raw.get("output.current")),
        line_frequency=_float_value(raw.get("input.frequency")),
        load_percent=_int_value(raw.get("ups.load")),
        load_va_percent=_int_value(raw.get("ups.load")),
        internal_temperature_c=_float_value(raw.get("ups.temperature")),
        nominal_output_voltage=_int_value(raw.get("output.voltage.nominal")) or 230,
        nominal_power_watts=_int_value(raw.get("ups.realpower.nominal")),
        nominal_va=_int_value(raw.get("ups.power.nominal")),
        min_battery_charge_percent=_int_value(raw.get("battery.charge.low")) or 10,
        min_runtime_minutes=round(_float_value(raw.get("battery.runtime.low")) / 60) or 5,
        source_backend="nut",
        raw=raw,
    )


def _parse_lines(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _float_value(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _int_value(value: str | None) -> int:
    return int(round(_float_value(value)))
