from __future__ import annotations

import json
import logging
import socket
import time
from threading import Event
from typing import Any

from pug.config import MqttConfig
from pug.frontends.homeassistant import discovery_payloads
from pug.raw_stats import raw_stats, state_payload
from pug.state import StateStore, UPSState

LOGGER = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(self, store: StateStore, config: MqttConfig) -> None:
        self.store = store
        self.config = config

    def run_forever(self, stop: Event) -> None:
        while not stop.is_set():
            try:
                state = self.store.get()
                publish_state(self.config, state)
                LOGGER.debug("published MQTT state to %s", self.config.topic_prefix)
            except Exception:
                LOGGER.exception("MQTT publish failed")
            stop.wait(self.config.publish_interval_seconds)


def publish_state(config: MqttConfig, state: UPSState) -> None:
    messages = mqtt_messages(config, state)

    with socket.create_connection((config.host, config.port), timeout=10) as sock:
        _send_connect(sock, config)
        for topic, body, retain in messages:
            _send_publish(sock, topic, body, retain=retain)
        sock.sendall(b"\xe0\x00")


def mqtt_messages(config: MqttConfig, state: UPSState) -> list[tuple[str, str, bool]]:
    payload = json.dumps(state_payload(state), sort_keys=True)
    messages: list[tuple[str, str, bool]] = [(config.topic_prefix, payload, False)]
    for key, value in normalized_topics(state).items():
        messages.append((f"{config.topic_prefix}/{key}", value, False))
    messages.extend(
        [
            (f"{config.topic_prefix}/status", state.status_text, False),
            (f"{config.topic_prefix}/online", _mqtt_bool(state.online), False),
            (f"{config.topic_prefix}/on_battery", _mqtt_bool(state.on_battery), False),
            (f"{config.topic_prefix}/replace_battery", _mqtt_bool(state.replace_battery), False),
        ]
    )
    messages.append((f"{config.topic_prefix}/raw", json.dumps(state.raw, sort_keys=True), False))
    for stat in raw_stats(state):
        messages.append((f"{config.topic_prefix}/raw/{stat.slug}", stat.value, False))
    for topic, discovery_payload in discovery_payloads(
        state,
        config.topic_prefix,
        config.discovery_prefix,
    ).items():
        messages.append((topic, json.dumps(discovery_payload, sort_keys=True), True))
    return messages


def normalized_topics(state: UPSState) -> dict[str, str]:
    values = {
        "battery_charge_percent": state.battery_charge_percent,
        "runtime_minutes": state.runtime_minutes,
        "seconds_on_battery": state.seconds_on_battery,
        "battery_voltage": state.battery_voltage,
        "input_voltage": state.input_voltage,
        "output_voltage": state.output_voltage,
        "output_current": state.output_current,
        "line_frequency": state.line_frequency,
        "load_percent": state.load_percent,
        "load_va_percent": state.load_va_percent,
        "internal_temperature_c": state.internal_temperature_c,
        "nominal_output_voltage": state.nominal_output_voltage,
        "nominal_power_watts": state.nominal_power_watts,
        "nominal_va": state.nominal_va,
        "min_battery_charge_percent": state.min_battery_charge_percent,
        "min_runtime_minutes": state.min_runtime_minutes,
    }
    return {key: str(value) for key, value in values.items()}


def _mqtt_bool(value: bool) -> str:
    return "ON" if value else "OFF"


def _send_connect(sock: socket.socket, config: MqttConfig) -> None:
    flags = 0x02
    payload = _utf8(config.client_id)
    if config.username:
        flags |= 0x80
        payload += _utf8(config.username)
    if config.password:
        flags |= 0x40
        payload += _utf8(config.password)
    variable_header = _utf8("MQTT") + bytes([4, flags]) + (60).to_bytes(2, "big")
    sock.sendall(bytes([0x10]) + _remaining_length(len(variable_header) + len(payload)) + variable_header + payload)
    connack = sock.recv(4)
    if len(connack) < 4 or connack[0] != 0x20 or connack[3] != 0:
        raise ConnectionError(f"MQTT broker rejected connection: {connack!r}")


def _send_publish(sock: socket.socket, topic: str, payload: str, retain: bool = False) -> None:
    body = _utf8(topic) + payload.encode("utf-8")
    fixed_header = 0x31 if retain else 0x30
    sock.sendall(bytes([fixed_header]) + _remaining_length(len(body)) + body)


def _utf8(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(2, "big") + encoded


def _remaining_length(length: int) -> bytes:
    encoded = bytearray()
    while True:
        byte = length % 128
        length //= 128
        if length:
            byte |= 128
        encoded.append(byte)
        if not length:
            return bytes(encoded)
