from __future__ import annotations

from pug.snmp.registry import oid
from pug.state import UPSState


@oid("1.3.6.1.2.1.33.1.1.1.0", type="string", name="upsIdentManufacturer")
def ups_manufacturer(state: UPSState) -> str:
    return state.manufacturer


@oid("1.3.6.1.2.1.33.1.1.2.0", type="string", name="upsIdentModel")
def ups_model(state: UPSState) -> str:
    return state.model


@oid("1.3.6.1.2.1.33.1.1.3.0", type="string", name="upsIdentUPSSoftwareVersion")
def ups_firmware(state: UPSState) -> str:
    return state.firmware


@oid("1.3.6.1.2.1.33.1.1.4.0", type="string", name="upsIdentAgentSoftwareVersion")
def ups_agent(_state: UPSState) -> str:
    return "PowerPi UPS Gateway"


@oid("1.3.6.1.2.1.33.1.1.5.0", type="string", name="upsIdentName")
def ups_name(state: UPSState) -> str:
    return state.name


@oid("1.3.6.1.2.1.33.1.2.1.0", type="integer", name="upsBatteryStatus")
def ups_battery_status(state: UPSState) -> int:
    if state.replace_battery:
        return 4
    if state.battery_charge_percent <= state.min_battery_charge_percent:
        return 3
    return 2


@oid("1.3.6.1.2.1.33.1.2.2.0", type="integer", name="upsSecondsOnBattery")
def ups_seconds_on_battery(state: UPSState) -> int:
    return state.seconds_on_battery


@oid("1.3.6.1.2.1.33.1.2.3.0", type="integer", name="upsEstimatedMinutesRemaining")
def ups_runtime(state: UPSState) -> int:
    return state.runtime_minutes


@oid("1.3.6.1.2.1.33.1.2.4.0", type="integer", name="upsEstimatedChargeRemaining")
def ups_charge(state: UPSState) -> int:
    return state.battery_charge_percent


@oid("1.3.6.1.2.1.33.1.4.1.0", type="integer", name="upsOutputSource")
def ups_output_source(state: UPSState) -> int:
    return 5 if state.on_battery else 3 if state.online else 1


@oid("1.3.6.1.2.1.33.1.4.4.1.2.1", type="integer", name="upsOutputVoltage")
def ups_output_voltage(state: UPSState) -> int:
    return round(state.output_voltage)


@oid("1.3.6.1.2.1.33.1.4.4.1.5.1", type="integer", name="upsOutputPercentLoad")
def ups_output_load(state: UPSState) -> int:
    return state.load_percent
