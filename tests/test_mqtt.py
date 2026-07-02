from pug.frontends.mqtt import _remaining_length


def test_mqtt_remaining_length_encoding() -> None:
    assert _remaining_length(0) == b"\x00"
    assert _remaining_length(127) == b"\x7f"
    assert _remaining_length(128) == b"\x80\x01"
    assert _remaining_length(321) == b"\xc1\x02"
