from pug.raw_stats import raw_stats, slugify, state_payload
from pug.snmp.apc_powernet import PUG_RAW_STATUS_BASE
from pug.snmp.registry import registry
from pug.state import UPSState


def test_raw_stats_extract_numeric_values_and_slugs() -> None:
    state = UPSState(raw={"LINEV": "221.7 Volts", "LASTXFER": "Line voltage notch or spike"})
    stats = {stat.key: stat for stat in raw_stats(state)}

    assert stats["LINEV"].slug == "linev"
    assert stats["LINEV"].number == 221.7
    assert stats["LASTXFER"].number is None


def test_state_payload_includes_raw_stats() -> None:
    payload = state_payload(UPSState(raw={"SELFTEST": "NG"}))

    assert payload["raw"]["SELFTEST"] == "NG"
    assert payload["raw_stats"]["selftest"]["value"] == "NG"


def test_raw_status_snmp_subtree_exposes_apcaccess_values() -> None:
    # LASTXFER is raw key 27, value column 2.
    entry = registry.resolve(f"{PUG_RAW_STATUS_BASE}.27.2.0")

    assert entry is not None
    assert entry.handler(UPSState(raw={"LASTXFER": "Line voltage notch or spike"})) == "Line voltage notch or spike"


def test_slugify_handles_apc_end_marker() -> None:
    assert slugify("END APC") == "end_apc"
