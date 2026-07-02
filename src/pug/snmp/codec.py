from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pug.snmp import ber


@dataclass(frozen=True)
class SnmpRequest:
    version: int
    community: str
    request_id: int
    pdu_tag: int
    oids: list[str]


@dataclass(frozen=True)
class SnmpValue:
    oid: str
    type: str
    value: Any


def decode_request(packet: bytes) -> SnmpRequest:
    root, end = ber.decode_tlv(packet)
    if end != len(packet) or root.tag != ber.SEQUENCE:
        raise ValueError("SNMP message must be a single sequence")

    offset = 0
    version_tlv, offset = ber.decode_tlv(root.value, offset)
    community_tlv, offset = ber.decode_tlv(root.value, offset)
    pdu_tlv, offset = ber.decode_tlv(root.value, offset)
    if version_tlv.tag != ber.INTEGER or community_tlv.tag != ber.OCTET_STRING:
        raise ValueError("invalid SNMP header")
    if pdu_tlv.tag not in {ber.GET_REQUEST, ber.GET_NEXT_REQUEST}:
        raise ValueError("only GET and GETNEXT requests are supported")

    pdu_offset = 0
    req_id_tlv, pdu_offset = ber.decode_tlv(pdu_tlv.value, pdu_offset)
    _error_tlv, pdu_offset = ber.decode_tlv(pdu_tlv.value, pdu_offset)
    _error_index_tlv, pdu_offset = ber.decode_tlv(pdu_tlv.value, pdu_offset)
    varbinds_tlv, pdu_offset = ber.decode_tlv(pdu_tlv.value, pdu_offset)
    if req_id_tlv.tag != ber.INTEGER or varbinds_tlv.tag != ber.SEQUENCE:
        raise ValueError("invalid SNMP PDU")

    oids: list[str] = []
    vb_offset = 0
    while vb_offset < len(varbinds_tlv.value):
        varbind_tlv, vb_offset = ber.decode_tlv(varbinds_tlv.value, vb_offset)
        if varbind_tlv.tag != ber.SEQUENCE:
            raise ValueError("invalid varbind")
        item_offset = 0
        oid_tlv, item_offset = ber.decode_tlv(varbind_tlv.value, item_offset)
        if oid_tlv.tag != ber.OBJECT_IDENTIFIER:
            raise ValueError("varbind missing OID")
        oids.append(ber.decode_oid(oid_tlv.value))

    return SnmpRequest(
        version=ber.decode_integer(version_tlv.value),
        community=community_tlv.value.decode("utf-8", errors="replace"),
        request_id=ber.decode_integer(req_id_tlv.value),
        pdu_tag=pdu_tlv.tag,
        oids=oids,
    )


def encode_response(request: SnmpRequest, values: list[SnmpValue]) -> bytes:
    varbinds = []
    for item in values:
        varbinds.append(
            ber.encode_sequence(
                ber.encode_oid(item.oid),
                _encode_value(item.type, item.value),
            )
        )
    pdu = ber.encode_sequence(
        ber.encode_integer(request.request_id),
        ber.encode_integer(0),
        ber.encode_integer(0),
        ber.encode_sequence(*varbinds),
        tag=ber.GET_RESPONSE,
    )
    return ber.encode_sequence(
        ber.encode_integer(request.version),
        ber.encode_octet_string(request.community),
        pdu,
    )


def encode_get_request(oid: str, request_id: int = 1, community: str = "public", version: int = 1) -> bytes:
    return _encode_request(ber.GET_REQUEST, oid, request_id, community, version)


def encode_get_next_request(oid: str, request_id: int = 1, community: str = "public", version: int = 1) -> bytes:
    return _encode_request(ber.GET_NEXT_REQUEST, oid, request_id, community, version)


def _encode_request(pdu_tag: int, oid: str, request_id: int, community: str, version: int) -> bytes:
    pdu = ber.encode_sequence(
        ber.encode_integer(request_id),
        ber.encode_integer(0),
        ber.encode_integer(0),
        ber.encode_sequence(ber.encode_sequence(ber.encode_oid(oid), ber.encode_null())),
        tag=pdu_tag,
    )
    return ber.encode_sequence(ber.encode_integer(version), ber.encode_octet_string(community), pdu)


def _encode_value(type_name: str, value: Any) -> bytes:
    if type_name == "integer":
        return ber.encode_integer(int(value))
    if type_name == "gauge":
        return ber.encode_unsigned(ber.GAUGE32, int(value))
    if type_name == "timeticks":
        return ber.encode_unsigned(ber.TIME_TICKS, int(value))
    if type_name == "string":
        return ber.encode_octet_string(str(value))
    if type_name == "oid":
        return ber.encode_oid(str(value))
    if type_name == "null":
        return ber.encode_null()
    if type_name == "noSuchObject":
        return ber.encode_no_such_object()
    raise ValueError(f"unsupported SNMP value type: {type_name}")
