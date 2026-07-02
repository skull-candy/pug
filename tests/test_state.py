from pug.collector.simulator import simulator_state
from pug.snmp import ber
from pug.snmp import apc_powernet as _apc_powernet  # noqa: F401
from pug.snmp import rfc1628 as _rfc1628  # noqa: F401
from pug.snmp.codec import decode_request, encode_get_next_request, encode_get_request
from pug.snmp.registry import registry
from pug.snmp.server import SnmpServer
from pug.state import StateStore


def test_simulated_state_qnap_discovery_oids() -> None:
    state = simulator_state()

    sys_object = registry.resolve("1.3.6.1.2.1.1.2.0")
    apc_model = registry.resolve("1.3.6.1.4.1.318.1.1.1.1.1.1.0")
    charge = registry.resolve("1.3.6.1.2.1.33.1.2.4.0")

    assert sys_object is not None
    assert apc_model is not None
    assert charge is not None
    assert sys_object.handler(state) == "1.3.6.1.4.1.318.1.1.1"
    assert apc_model.handler(state) == "Smart-UPS 3000"
    assert charge.handler(state) == 100


def test_get_request_decoder() -> None:
    request = decode_request(encode_get_request("1.3.6.1.2.1.1.2.0", request_id=42))

    assert request.community == "public"
    assert request.request_id == 42
    assert request.oids == ["1.3.6.1.2.1.1.2.0"]


def test_snmp_getnext_returns_next_registered_oid() -> None:
    server = SnmpServer(StateStore(simulator_state()), port=0, developer_log=False)
    response = server.handle_packet(
        encode_get_next_request("1.3.6.1.2.1.1.1.0", request_id=7),
        "127.0.0.1",
    )

    assert response is not None
    assert _first_response_oid(response) == "1.3.6.1.2.1.1.2.0"


def _first_response_oid(packet: bytes) -> str:
    root, _end = ber.decode_tlv(packet)
    offset = 0
    _version, offset = ber.decode_tlv(root.value, offset)
    _community, offset = ber.decode_tlv(root.value, offset)
    pdu, _offset = ber.decode_tlv(root.value, offset)
    pdu_offset = 0
    _request_id, pdu_offset = ber.decode_tlv(pdu.value, pdu_offset)
    _error_status, pdu_offset = ber.decode_tlv(pdu.value, pdu_offset)
    _error_index, pdu_offset = ber.decode_tlv(pdu.value, pdu_offset)
    varbinds, _pdu_offset = ber.decode_tlv(pdu.value, pdu_offset)
    varbind, _vb_offset = ber.decode_tlv(varbinds.value, 0)
    oid_value, _item_offset = ber.decode_tlv(varbind.value, 0)
    return ber.decode_oid(oid_value.value)
