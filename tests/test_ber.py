from pug.snmp.ber import decode_oid, decode_tlv, encode_integer, encode_oid


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
