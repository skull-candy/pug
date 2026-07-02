from __future__ import annotations

from dataclasses import dataclass


INTEGER = 0x02
OCTET_STRING = 0x04
NULL = 0x05
OBJECT_IDENTIFIER = 0x06
SEQUENCE = 0x30
GET_REQUEST = 0xA0
GET_NEXT_REQUEST = 0xA1
GET_RESPONSE = 0xA2
NO_SUCH_OBJECT = 0x80


@dataclass(frozen=True)
class BerValue:
    tag: int
    value: bytes


def encode_tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + encode_length(len(value)) + value


def encode_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    data = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(data)]) + data


def decode_tlv(data: bytes, offset: int = 0) -> tuple[BerValue, int]:
    if offset >= len(data):
        raise ValueError("missing BER tag")
    tag = data[offset]
    length, offset = decode_length(data, offset + 1)
    end = offset + length
    if end > len(data):
        raise ValueError("BER value extends beyond packet")
    return BerValue(tag, data[offset:end]), end


def decode_length(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data):
        raise ValueError("missing BER length")
    first = data[offset]
    offset += 1
    if first < 0x80:
        return first, offset
    count = first & 0x7F
    if count == 0:
        raise ValueError("indefinite BER length is not supported")
    if offset + count > len(data):
        raise ValueError("truncated BER length")
    return int.from_bytes(data[offset : offset + count], "big"), offset + count


def encode_integer(value: int) -> bytes:
    if value == 0:
        raw = b"\x00"
    else:
        byte_len = max(1, (value.bit_length() + 8) // 8)
        raw = value.to_bytes(byte_len, "big", signed=True)
        while len(raw) > 1 and raw[0] == 0 and not raw[1] & 0x80:
            raw = raw[1:]
        while len(raw) > 1 and raw[0] == 0xFF and raw[1] & 0x80:
            raw = raw[1:]
    return encode_tlv(INTEGER, raw)


def decode_integer(value: bytes) -> int:
    if not value:
        return 0
    return int.from_bytes(value, "big", signed=True)


def encode_octet_string(value: str | bytes) -> bytes:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return encode_tlv(OCTET_STRING, raw)


def encode_null() -> bytes:
    return encode_tlv(NULL, b"")


def encode_no_such_object() -> bytes:
    return encode_tlv(NO_SUCH_OBJECT, b"")


def encode_sequence(*items: bytes, tag: int = SEQUENCE) -> bytes:
    return encode_tlv(tag, b"".join(items))


def encode_oid(oid: str) -> bytes:
    parts = [int(part) for part in oid.split(".")]
    if len(parts) < 2:
        raise ValueError("OID must have at least two arcs")
    if parts[0] not in {0, 1, 2}:
        raise ValueError("first OID arc must be 0, 1, or 2")
    if parts[0] < 2 and parts[1] > 39:
        raise ValueError("second OID arc must be 0..39 when first arc is 0 or 1")
    encoded = _encode_base128(parts[0] * 40 + parts[1])
    for part in parts[2:]:
        encoded += _encode_base128(part)
    return encode_tlv(OBJECT_IDENTIFIER, encoded)


def decode_oid(value: bytes) -> str:
    if not value:
        raise ValueError("empty OID")
    first_subid, offset = _decode_base128(value, 0)
    if first_subid < 40:
        parts = [0, first_subid]
    elif first_subid < 80:
        parts = [1, first_subid - 40]
    else:
        parts = [2, first_subid - 80]
    while offset < len(value):
        part, offset = _decode_base128(value, offset)
        parts.append(part)
    return ".".join(str(part) for part in parts)


def _encode_base128(value: int) -> bytes:
    if value < 0:
        raise ValueError("OID arcs must be non-negative")
    stack = [value & 0x7F]
    value >>= 7
    while value:
        stack.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(stack))


def _decode_base128(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    while True:
        if offset >= len(data):
            raise ValueError("truncated OID arc")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset
