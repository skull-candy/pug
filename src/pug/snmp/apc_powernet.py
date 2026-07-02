from __future__ import annotations

from pug.snmp.registry import oid, registry
from pug.state import UPSState

APC_SMART_UPS_OID = "1.3.6.1.4.1.318.1.1.1"
PUG_RAW_STATUS_BASE = "1.3.6.1.4.1.318.1.1.1.99.1"
APC_BATTERY_UNKNOWN = 1
APC_BATTERY_NORMAL = 2
APC_BATTERY_LOW = 3
APC_BATTERY_REPLACE = 4
APC_OUTPUT_UNKNOWN = 1
APC_OUTPUT_ON_LINE = 2
APC_OUTPUT_ON_BATTERY = 3


@oid("1.3.6.1.2.1.1.1.0", type="string", name="sysDescr")
def sys_descr(state: UPSState) -> str:
    return f"APC {state.model} via PowerPi UPS Gateway"


@oid("1.3.6.1.2.1.1.2.0", type="oid", name="sysObjectID")
def sys_object_id(_state: UPSState) -> str:
    return APC_SMART_UPS_OID


@oid("1.3.6.1.2.1.1.5.0", type="string", name="sysName")
def sys_name(state: UPSState) -> str:
    return state.name


@oid("1.3.6.1.4.1.318.1.1.1.1.1.1.0", type="string", name="upsBasicIdentModel")
def apc_model(state: UPSState) -> str:
    return state.model


@oid("1.3.6.1.4.1.318.1.1.1.2.1.1.0", type="integer", name="upsBasicBatteryStatus")
def apc_basic_battery_status(state: UPSState) -> int:
    return apc_battery_status_value(state)


@oid("1.3.6.1.4.1.318.1.1.1.2.1.2.0", type="timeticks", name="upsBasicBatteryTimeOnBattery")
def apc_basic_time_on_battery(state: UPSState) -> int:
    return seconds_to_timeticks(state.seconds_on_battery)


@oid("1.3.6.1.4.1.318.1.1.1.2.1.3.0", type="string", name="upsBasicBatteryLastReplaceDate")
def apc_battery_last_replace_date(state: UPSState) -> str:
    return state.battery_date


@oid("1.3.6.1.4.1.318.1.1.1.2.2.1.0", type="gauge", name="upsAdvBatteryCapacity")
def apc_battery_charge(state: UPSState) -> int:
    return state.battery_charge_percent


@oid("1.3.6.1.4.1.318.1.1.1.2.2.2.0", type="integer", name="upsAdvBatteryTemperature")
def apc_temperature(state: UPSState) -> int:
    return round(state.internal_temperature_c)


@oid("1.3.6.1.4.1.318.1.1.1.2.2.3.0", type="timeticks", name="upsAdvBatteryRunTimeRemaining")
def apc_runtime_timeticks(state: UPSState) -> int:
    return minutes_to_timeticks(state.runtime_minutes)


@oid("1.3.6.1.4.1.318.1.1.1.2.2.4.0", type="integer", name="upsAdvBatteryReplaceIndicator")
def apc_replace_indicator(state: UPSState) -> int:
    return 2 if state.replace_battery else 1


@oid("1.3.6.1.4.1.318.1.1.1.2.2.7.0", type="integer", name="upsAdvBatteryNominalVoltage")
def apc_nominal_battery_voltage(state: UPSState) -> int:
    return round(state.battery_voltage) if state.battery_voltage else 0


@oid("1.3.6.1.4.1.318.1.1.1.2.2.8.0", type="integer", name="upsAdvBatteryActualVoltage")
def apc_battery_voltage(state: UPSState) -> int:
    return round(state.battery_voltage)


@oid("1.3.6.1.4.1.318.1.1.1.2.2.99.1.0", type="integer", name="pugBatteryStatus")
def pug_battery_status(state: UPSState) -> int:
    return apc_battery_status_value(state)


@oid("1.3.6.1.4.1.318.1.1.1.2.2.99.2.0", type="integer", name="pugSecondsOnBattery")
def pug_seconds_on_battery(state: UPSState) -> int:
    return state.seconds_on_battery


@oid("1.3.6.1.4.1.318.1.1.1.3.2.1.0", type="integer", name="upsAdvInputLineVoltage")
def apc_input_voltage(state: UPSState) -> int:
    return round(state.input_voltage)


@oid("1.3.6.1.4.1.318.1.1.1.4.2.1.0", type="integer", name="upsAdvOutputVoltage")
def apc_output_voltage(state: UPSState) -> int:
    return round(state.output_voltage)


@oid("1.3.6.1.4.1.318.1.1.1.4.2.3.0", type="integer", name="upsAdvOutputLoad")
def apc_output_load(state: UPSState) -> int:
    return state.load_percent


@oid("1.3.6.1.4.1.318.1.1.1.4.2.4.0", type="integer", name="upsAdvOutputCurrent")
def apc_output_current(state: UPSState) -> int:
    return round(state.output_current)


@oid("1.3.6.1.4.1.318.1.1.1.4.2.5.0", type="integer", name="upsAdvOutputSource")
def apc_output_source(state: UPSState) -> int:
    return apc_output_source_value(state)


@oid("1.3.6.1.4.1.318.1.1.1.5.2.1.0", type="integer", name="upsAdvConfigRatedOutputVoltage")
def apc_nominal_output_voltage(state: UPSState) -> int:
    return state.nominal_output_voltage


@oid("1.3.6.1.4.1.318.1.1.1.5.2.2.0", type="integer", name="upsAdvConfigHighTransferVolt")
def apc_nominal_power_watts(state: UPSState) -> int:
    return state.nominal_power_watts


@oid("1.3.6.1.4.1.318.1.1.1.5.2.3.0", type="integer", name="upsAdvConfigLowTransferVolt")
def apc_nominal_va(state: UPSState) -> int:
    return state.nominal_va


@oid("1.3.6.1.4.1.318.1.1.1.5.2.8.0", type="integer", name="upsAdvConfigLowBatteryWarning")
def apc_min_charge(state: UPSState) -> int:
    return state.min_battery_charge_percent


@oid("1.3.6.1.4.1.318.1.1.1.5.2.14.0", type="integer", name="upsAdvConfigReturnRuntime")
def apc_min_runtime(state: UPSState) -> int:
    return state.min_runtime_minutes


def apc_battery_status_value(state: UPSState) -> int:
    if state.replace_battery:
        return APC_BATTERY_REPLACE
    if state.battery_charge_percent <= state.min_battery_charge_percent:
        return APC_BATTERY_LOW
    if state.on_battery:
        return APC_BATTERY_LOW
    return APC_BATTERY_NORMAL if state.online else APC_BATTERY_UNKNOWN


def apc_output_source_value(state: UPSState) -> int:
    if state.on_battery:
        return APC_OUTPUT_ON_BATTERY
    if state.online:
        return APC_OUTPUT_ON_LINE
    return APC_OUTPUT_UNKNOWN


def seconds_to_timeticks(seconds: int) -> int:
    return max(0, int(round(seconds * 100)))


def minutes_to_timeticks(minutes: int) -> int:
    return seconds_to_timeticks(minutes * 60)


def _register_raw_status_oids() -> None:
    keys = [
        "APC",
        "DATE",
        "HOSTNAME",
        "VERSION",
        "UPSNAME",
        "CABLE",
        "DRIVER",
        "UPSMODE",
        "STARTTIME",
        "MODEL",
        "STATUS",
        "LINEV",
        "LOADPCT",
        "LOADAPNT",
        "BCHARGE",
        "TIMELEFT",
        "MBATTCHG",
        "MINTIMEL",
        "MAXTIME",
        "OUTPUTV",
        "DWAKE",
        "DSHUTD",
        "ITEMP",
        "BATTV",
        "LINEFREQ",
        "OUTCURNT",
        "LASTXFER",
        "NUMXFERS",
        "XONBATT",
        "TONBATT",
        "CUMONBATT",
        "XOFFBATT",
        "SELFTEST",
        "STATFLAG",
        "MANDATE",
        "SERIALNO",
        "BATTDATE",
        "NOMOUTV",
        "NOMPOWER",
        "NOMAPNT",
        "FIRMWARE",
        "END APC",
    ]
    for index, key in enumerate(keys, start=1):
        registry.register(
            f"{PUG_RAW_STATUS_BASE}.{index}.1.0",
            "string",
            f"pugRaw{key.replace(' ', '')}Key",
            _raw_key_handler(key),
        )
        registry.register(
            f"{PUG_RAW_STATUS_BASE}.{index}.2.0",
            "string",
            f"pugRaw{key.replace(' ', '')}Value",
            _raw_value_handler(key),
        )


def _raw_key_handler(key: str):
    def handler(_state: UPSState) -> str:
        return key

    return handler


def _raw_value_handler(key: str):
    def handler(state: UPSState) -> str:
        return str(state.raw.get(key, ""))

    return handler


_register_raw_status_oids()
