from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pug.state import UPSState


SnmpType = str
Handler = Callable[[UPSState], Any]


@dataclass(frozen=True)
class OidEntry:
    oid: str
    type: SnmpType
    name: str
    handler: Handler


class OidRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, OidEntry] = {}

    def register(self, oid_value: str, type: SnmpType, name: str, handler: Handler) -> Handler:
        self._entries[oid_value] = OidEntry(oid_value, type, name, handler)
        return handler

    def resolve(self, oid_value: str) -> OidEntry | None:
        return self._entries.get(oid_value)

    def next_after(self, oid_value: str) -> OidEntry | None:
        requested = _oid_key(oid_value)
        for entry in sorted(self._entries.values(), key=lambda item: _oid_key(item.oid)):
            if _oid_key(entry.oid) > requested:
                return entry
        return None

    def values(self) -> list[OidEntry]:
        return list(self._entries.values())


registry = OidRegistry()


def oid(oid_value: str, type: SnmpType, name: str) -> Callable[[Handler], Handler]:
    def decorator(func: Handler) -> Handler:
        return registry.register(oid_value, type, name, func)

    return decorator


def _oid_key(oid_value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in oid_value.split("."))
