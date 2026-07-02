from pug.collector.apcupsd import parse_apcupsd_status
from pug.snmp import apc_powernet as _apc_powernet  # noqa: F401
from pug.snmp.apc_powernet import minutes_to_timeticks
from pug.snmp.registry import registry


REAL_SAMPLE = """MODEL    : Smart-UPS 3000
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
BATTDATE : 2026-06-14
NOMOUTV  : 230 Volts
NOMPOWER : 2700 Watts
NOMAPNT  : 3000 VA
"""


def test_librenms_apc_battery_oids_match_real_apcaccess_sample() -> None:
    state = parse_apcupsd_status(REAL_SAMPLE)

    assert _value("1.3.6.1.4.1.318.1.1.1.2.2.1.0", state) == 100
    assert _value("1.3.6.1.4.1.318.1.1.1.2.2.2.0", state) == 26
    assert _value("1.3.6.1.4.1.318.1.1.1.2.2.3.0", state) == minutes_to_timeticks(38)
    assert _value("1.3.6.1.4.1.318.1.1.1.2.2.4.0", state) == 2
    assert _value("1.3.6.1.4.1.318.1.1.1.2.2.8.0", state) == 54
    assert _value("1.3.6.1.4.1.318.1.1.1.3.2.1.0", state) == 225
    assert _value("1.3.6.1.4.1.318.1.1.1.4.2.1.0", state) == 223
    assert _value("1.3.6.1.4.1.318.1.1.1.4.2.3.0", state) == 27


def _value(oid: str, state):
    entry = registry.resolve(oid)
    assert entry is not None
    return entry.handler(state)
