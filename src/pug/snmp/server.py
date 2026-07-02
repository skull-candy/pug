from __future__ import annotations

import logging
import socket
from threading import Event

from pug.snmp import ber
from pug.snmp.codec import SnmpValue, decode_request, encode_response
from pug.snmp.registry import registry
from pug.state import StateStore

LOGGER = logging.getLogger(__name__)


class SnmpServer:
    def __init__(
        self,
        store: StateStore,
        listen: str = "0.0.0.0",
        port: int = 161,
        community: str = "public",
        developer_log: bool = True,
    ) -> None:
        self.store = store
        self.listen = listen
        self.port = port
        self.community = community
        self.developer_log = developer_log

    def serve_forever(self, stop: Event | None = None) -> None:
        stop = stop or Event()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((self.listen, self.port))
            sock.settimeout(1.0)
            LOGGER.info("SNMP listening on %s:%s", self.listen, self.port)
            while not stop.is_set():
                try:
                    packet, address = sock.recvfrom(8192)
                except TimeoutError:
                    continue
                except socket.timeout:
                    continue
                response = self.handle_packet(packet, address[0])
                if response:
                    sock.sendto(response, address)

    def handle_packet(self, packet: bytes, client_ip: str) -> bytes | None:
        try:
            request = decode_request(packet)
        except ValueError as exc:
            LOGGER.debug("dropping invalid SNMP packet from %s: %s", client_ip, exc)
            return None

        if request.community != self.community:
            LOGGER.warning("dropping SNMP packet from %s with wrong community", client_ip)
            return None

        state = self.store.get()
        values: list[SnmpValue] = []
        for oid_value in request.oids:
            response_oid = oid_value
            if request.pdu_tag == ber.GET_REQUEST:
                entry = registry.resolve(oid_value)
            elif request.pdu_tag == ber.GET_NEXT_REQUEST:
                entry = registry.next_after(oid_value)
                if entry is not None:
                    response_oid = entry.oid
            else:
                entry = None
            if entry is None:
                if self.developer_log:
                    LOGGER.info("[MISS] %s %s", client_ip, oid_value)
                values.append(SnmpValue(oid_value, "noSuchObject", None))
                continue
            value = entry.handler(state)
            if self.developer_log:
                LOGGER.info("[HIT ] %s %s %s %r", client_ip, response_oid, entry.name, value)
            values.append(SnmpValue(response_oid, entry.type, value))

        return encode_response(request, values)
