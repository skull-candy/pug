from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence

from pug.collector.base import Collector
from pug.state import UPSState


_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


class ApcupsdCollector(Collector):
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
        return parse_apcupsd_status(result.stdout)


def parse_apcupsd_status(text: str) -> UPSState:
    raw = _parse_lines(text)
    status = raw.get("STATUS", "UNKNOWN")
    status_tokens = set(status.upper().split())

    return UPSState(
        manufacturer="APC",
        model=raw.get("MODEL", "Smart-UPS 3000"),
        name=raw.get("UPSNAME", raw.get("MODEL", "PowerPi UPS")),
        serial=raw.get("SERIALNO", ""),
        firmware=raw.get("FIRMWARE", ""),
        manufacture_date=raw.get("MANDATE", ""),
        battery_date=raw.get("BATTDATE", ""),
        status_text=status,
        online="ONLINE" in status_tokens,
        on_battery=bool({"ONBATT", "LOWBATT"} & status_tokens),
        replace_battery="REPLACEBATT" in status_tokens,
        battery_charge_percent=_int_value(raw.get("BCHARGE")),
        runtime_minutes=_int_value(raw.get("TIMELEFT")),
        seconds_on_battery=_int_value(raw.get("CUMONBATT")) or _int_value(raw.get("TONBATT")),
        battery_voltage=_float_value(raw.get("BATTV")),
        input_voltage=_float_value(raw.get("LINEV")),
        output_voltage=_float_value(raw.get("OUTPUTV")),
        output_current=_float_value(raw.get("OUTCURNT")),
        line_frequency=_float_value(raw.get("LINEFREQ")),
        load_percent=_int_value(raw.get("LOADPCT")),
        load_va_percent=_int_value(raw.get("LOADAPNT")) or _int_value(raw.get("LOADPCT")),
        internal_temperature_c=_float_value(raw.get("ITEMP")),
        nominal_output_voltage=_int_value(raw.get("NOMOUTV")) or 230,
        nominal_power_watts=_int_value(raw.get("NOMPOWER")),
        nominal_va=_int_value(raw.get("NOMAPNT")),
        min_battery_charge_percent=_int_value(raw.get("MBATTCHG")) or 10,
        min_runtime_minutes=_int_value(raw.get("MINTIMEL")) or 5,
        source_backend="apcupsd",
        raw=raw,
    )


def _parse_lines(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip().upper()] = value.strip()
    return parsed


def _float_value(value: str | None) -> float:
    if not value:
        return 0.0
    match = _NUMBER_RE.search(value)
    return float(match.group(0)) if match else 0.0


def _int_value(value: str | None) -> int:
    return int(round(_float_value(value)))
