from __future__ import annotations

from typing import Any

from sources.models import Source

from .normalizer import SOURCE_PRECEDENCE_VERSION


def source_precedence_rank(source: Source) -> int:
    searchable = " ".join(
        str(value or "").casefold()
        for value in (
            source.source_type,
            source.platform_family,
            source.source_name,
        )
    )
    if "aggregator" in searchable or "general" in searchable or "regional" in searchable:
        return 6
    if "discovery" in searchable or "public_portal" in searchable:
        return 5
    if "sector" in searchable or "specialist" in searchable:
        return 4
    if "ett" in searchable or "staff" in searchable or "agency" in searchable:
        return 3
    if "private" in searchable and "direct" in searchable:
        return 2
    return 1


def precedence_evidence(source: Source) -> dict[str, Any]:
    return {
        "version": SOURCE_PRECEDENCE_VERSION,
        "rank": source_precedence_rank(source),
        "source_id": source.source_id,
        "source_type": source.source_type,
        "platform_family": source.platform_family,
    }
