from __future__ import annotations

from pug.state import UPSState


def simulator_state() -> UPSState:
    return UPSState(
        manufacturer="APC",
        model="Smart-UPS 3000",
        name="PowerPi Simulator",
        serial="SIM0000001",
        firmware="UPS 09.3 / 00.4",
        status_text="ONLINE",
        online=True,
        on_battery=False,
        replace_battery=False,
        battery_charge_percent=100,
        runtime_minutes=54,
        seconds_on_battery=0,
        battery_voltage=54.0,
        input_voltage=230.4,
        output_voltage=230.4,
        output_current=3.41,
        line_frequency=50.0,
        load_percent=26,
        load_va_percent=26,
        internal_temperature_c=30.1,
        nominal_output_voltage=230,
        nominal_power_watts=2700,
        nominal_va=3000,
        min_battery_charge_percent=10,
        min_runtime_minutes=5,
        source_backend="simulator",
        raw={"simulator": True},
    )
