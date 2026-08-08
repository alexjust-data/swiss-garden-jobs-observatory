from __future__ import annotations

import re
from dataclasses import dataclass

from .normalizer import POSITION_COUNT_VERSION

_EXPLICIT = re.compile(
    r"(?<![%\d])\b([1-9]\d?)\s+"
    r"(mitarbeit(?:ende|er(?:innen)?|er\s*/\s*innen)|personen|stellen)\b",
    re.IGNORECASE,
)
_MULTI = re.compile(
    r"\b(mehrere\s+(?:mitarbeit\w*|stellen)|lehrstellen|laufend\s+gesucht)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PositionCountResult:
    positions_count: int | None
    multi_hire_possible: bool
    method: str
    raw_evidence: str


def extract_position_count(text: str) -> PositionCountResult:
    match = _EXPLICIT.search(text)
    if match:
        return PositionCountResult(int(match.group(1)), True, "EXPLICIT_NUMERIC", match.group(0))
    match = _MULTI.search(text)
    if match:
        return PositionCountResult(None, True, "EXPLICIT_PLURAL", match.group(0))
    return PositionCountResult(None, False, "NO_EXPLICIT_EVIDENCE", "")


__all__ = ["POSITION_COUNT_VERSION", "PositionCountResult", "extract_position_count"]
