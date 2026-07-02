from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pug.state import UPSState

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_KEY_RE = re.compile(r"[^a-zA-Z0-9_]+")


@dataclass(frozen=True)
class RawStat:
    key: str
    slug: str
    value: str
    number: float | None


def raw_stats(state: UPSState) -> list[RawStat]:
    stats = []
    for key, value in sorted(state.raw.items()):
        text = str(value)
        stats.append(RawStat(key=key, slug=slugify(key), value=text, number=parse_number(text)))
    return stats


def slugify(value: str) -> str:
    slug = _KEY_RE.sub("_", value.strip().lower()).strip("_")
    return slug or "value"


def parse_number(value: str) -> float | None:
    match = _NUMBER_RE.search(value)
    return float(match.group(0)) if match else None


def state_payload(state: UPSState) -> dict[str, Any]:
    data = state.to_dict()
    data["raw_stats"] = {
        stat.slug: {"key": stat.key, "value": stat.value, "number": stat.number}
        for stat in raw_stats(state)
    }
    return data
