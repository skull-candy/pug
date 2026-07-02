from pug.collector.simulator import simulator_state
from pug.snmp.apc_powernet import apc_battery_status_value, apc_output_source_value


def test_apc_enums_for_online_state() -> None:
    state = simulator_state()

    assert apc_battery_status_value(state) == 2
    assert apc_output_source_value(state) == 2


def test_apc_enums_for_on_battery_state() -> None:
    state = simulator_state().updated(online=False, on_battery=True)

    assert apc_battery_status_value(state) == 3
    assert apc_output_source_value(state) == 3


def test_apc_enums_for_replace_battery_state() -> None:
    state = simulator_state().updated(replace_battery=True)

    assert apc_battery_status_value(state) == 4


def test_apc_enums_for_unknown_state() -> None:
    state = simulator_state().updated(online=False, on_battery=False)

    assert apc_battery_status_value(state) == 1
    assert apc_output_source_value(state) == 1
