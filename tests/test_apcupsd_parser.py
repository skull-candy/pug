from pug.collector.apcupsd import parse_apcupsd_status


SAMPLE = """MODEL    : Smart-UPS 3000
STATUS   : ONLINE REPLACEBATT
LINEV    : 230.4 Volts
LOADPCT  : 26.0 Percent
BCHARGE  : 100.0 Percent
TIMELEFT : 54.0 Minutes
OUTPUTV  : 230.4 Volts
ITEMP    : 30.1 C
BATTV    : 54.0 Volts
LINEFREQ : 50.0 Hz
OUTCURNT : 3.41 Amps
SERIALNO : AS1626253281
NOMPOWER : 2700 Watts
NOMAPNT  : 3000 VA
FIRMWARE : UPS 09.3 / 00.4
"""


def test_parse_apcupsd_sample() -> None:
    state = parse_apcupsd_status(SAMPLE)

    assert state.model == "Smart-UPS 3000"
    assert state.online is True
    assert state.replace_battery is True
    assert state.battery_charge_percent == 100
    assert state.runtime_minutes == 54
    assert state.output_current == 3.41
    assert state.load_va_percent == 26
    assert state.serial == "AS1626253281"
    assert state.nominal_power_watts == 2700
    assert state.nominal_va == 3000


def test_parse_real_apcupsd_sample_for_librenms_values() -> None:
    sample = """MODEL    : Smart-UPS 3000
STATUS   : ONLINE REPLACEBATT
LINEV    : 224.6 Volts
LOADPCT  : 26.6 Percent
LOADAPNT : 28.6 Percent
BCHARGE  : 100.0 Percent
TIMELEFT : 38.0 Minutes
MBATTCHG : 5 Percent
MINTIMEL : 3 Minutes
OUTPUTV  : 223.2 Volts
ITEMP    : 26.1 C
BATTV    : 54.5 Volts
LINEFREQ : 50.0 Hz
OUTCURNT : 3.84 Amps
CUMONBATT: 19 Seconds
SERIALNO : AS1626253281
NOMPOWER : 2700 Watts
NOMAPNT  : 3000 VA
FIRMWARE : UPS 09.3 / 00.4
"""
    state = parse_apcupsd_status(sample)

    assert state.battery_charge_percent == 100
    assert state.runtime_minutes == 38
    assert state.internal_temperature_c == 26.1
    assert state.battery_voltage == 54.5
    assert state.input_voltage == 224.6
    assert state.output_voltage == 223.2
    assert state.load_percent == 27
    assert state.load_va_percent == 29
