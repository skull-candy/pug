from pug.snmp.ber import GAUGE32, TIME_TICKS, decode_oid, decode_tlv, encode_integer, encode_oid, encode_unsigned


def test_oid_round_trip() -> None:
    encoded = encode_oid("1.3.6.1.4.1.318.1.1.1")
    tlv, end = decode_tlv(encoded)

    assert end == len(encoded)
    assert decode_oid(tlv.value) == "1.3.6.1.4.1.318.1.1.1"


def test_oid_round_trip_with_large_second_arc() -> None:
    encoded = encode_oid("2.999.3.4000.1")
    tlv, end = decode_tlv(encoded)

    assert end == len(encoded)
    assert decode_oid(tlv.value) == "2.999.3.4000.1"


def test_integer_encodes_minimal_positive_value() -> None:
    assert encode_integer(127) == b"\x02\x01\x7f"
    assert encode_integer(128) == b"\x02\x02\x00\x80"


def test_unsigned_application_types_encode_with_expected_tags() -> None:
    assert encode_unsigned(GAUGE32, 100) == b"\x42\x01\x64"
    assert encode_unsigned(TIME_TICKS, 228000) == b"\x43\x03\x03\x7a\xa0"
