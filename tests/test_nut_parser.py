from pug.collector.nut import parse_nut_status


SAMPLE = """device.mfr: APC
device.model: Smart-UPS 1500
device.serial: AS123
ups.status: OL
battery.charge: 98
battery.runtime: 1800
battery.voltage: 27.2
input.voltage: 230.1
output.voltage: 229.8
ups.load: 31
ups.realpower.nominal: 900
ups.power.nominal: 1500
"""


def test_parse_nut_status() -> None:
    state = parse_nut_status(SAMPLE)

    assert state.manufacturer == "APC"
    assert state.model == "Smart-UPS 1500"
    assert state.online is True
    assert state.on_battery is False
    assert state.battery_charge_percent == 98
    assert state.runtime_minutes == 30
    assert state.nominal_power_watts == 900
    assert state.nominal_va == 1500
