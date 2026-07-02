from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class UPSState:
    manufacturer: str = "APC"
    model: str = "Smart-UPS 3000"
    name: str = "PowerPi UPS"
    serial: str = ""
    firmware: str = ""
    manufacture_date: str = ""
    battery_date: str = ""
    status_text: str = "UNKNOWN"
    online: bool = False
    on_battery: bool = False
    replace_battery: bool = False
    battery_charge_percent: int = 0
    runtime_minutes: int = 0
    seconds_on_battery: int = 0
    battery_voltage: float = 0.0
    input_voltage: float = 0.0
    output_voltage: float = 0.0
    output_current: float = 0.0
    line_frequency: float = 0.0
    load_percent: int = 0
    load_va_percent: int = 0
    internal_temperature_c: float = 0.0
    nominal_output_voltage: int = 230
    nominal_power_watts: int = 0
    nominal_va: int = 0
    min_battery_charge_percent: int = 10
    min_runtime_minutes: int = 5
    last_update: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_backend: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def updated(self, **changes: Any) -> "UPSState":
        if "last_update" not in changes:
            changes["last_update"] = datetime.now(timezone.utc)
        return replace(self, **changes)


class StateStore:
    def __init__(self, initial: UPSState | None = None) -> None:
        self._state = initial or UPSState()
        self._lock = Lock()

    def get(self) -> UPSState:
        with self._lock:
            return self._state

    def set(self, state: UPSState) -> None:
        with self._lock:
            self._state = state
