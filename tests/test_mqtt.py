from pug.config import MqttConfig
from pug.frontends.mqtt import _remaining_length, mqtt_messages, normalized_topics, rediscovery_messages
from pug.state import UPSState


def test_mqtt_remaining_length_encoding() -> None:
    assert _remaining_length(0) == b"\x00"
    assert _remaining_length(127) == b"\x7f"
    assert _remaining_length(128) == b"\x80\x01"
    assert _remaining_length(321) == b"\xc1\x02"


def test_mqtt_messages_include_raw_topics() -> None:
    messages = mqtt_messages(MqttConfig(), UPSState(raw={"SELFTEST": "NG"}))
    topics = {topic: payload for topic, payload, _retain in messages}

    assert "powerpi/ups/raw" in topics
    assert topics["powerpi/ups/raw/selftest"] == "NG"


def test_mqtt_messages_include_status_topics() -> None:
    messages = mqtt_messages(
        MqttConfig(),
        UPSState(status_text="ONLINE REPLACEBATT", online=True, replace_battery=True),
    )
    topics = {topic: payload for topic, payload, _retain in messages}

    assert topics["powerpi/ups/status"] == "ONLINE REPLACEBATT"
    assert topics["powerpi/ups/online"] == "ON"
    assert topics["powerpi/ups/on_battery"] == "OFF"
    assert topics["powerpi/ups/replace_battery"] == "ON"


def test_mqtt_messages_include_normalized_temperature_topic() -> None:
    state = UPSState(internal_temperature_c=27.0)
    messages = mqtt_messages(MqttConfig(), state)
    topics = {topic: payload for topic, payload, _retain in messages}

    assert normalized_topics(state)["internal_temperature_c"] == "27.0"
    assert topics["powerpi/ups/internal_temperature_c"] == "27.0"


def test_rediscovery_messages_clear_then_republish_discovery_topics() -> None:
    messages = rediscovery_messages(MqttConfig(), UPSState(raw={"SELFTEST": "NG"}))
    discovery_topic = "homeassistant/sensor/powerpi_ups/status/config"

    first = next(message for message in messages if message[0] == discovery_topic)
    last = [message for message in messages if message[0] == discovery_topic][-1]

    assert first == (discovery_topic, "", True)
    assert '"unique_id": "powerpi_ups_status"' in last[1]
    assert last[2] is True
