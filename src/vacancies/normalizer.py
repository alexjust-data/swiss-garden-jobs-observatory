from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DEDUP_VERSION = "dedup-v0.1"
NORMALIZER_VERSION = "dedup-normalizer-v0.1"
POSITION_COUNT_VERSION = "position-count-v0.1"
SOURCE_PRECEDENCE_VERSION = "source-precedence-v0.1"
REPOST_WINDOW_DAYS = 90

_TRACKING_KEYS = {"gclid", "fbclid", "sessionid", "tracking", "trk"}
_REQUISITION_KEYS = {
    "successfactors_requisition_id",
    "requisition_id",
    "requisitionid",
    "jobreqid",
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"(?<=\w)[:*Â·/](?=in\b)", "", normalized)
    normalized = re.sub(r"[^\w%]+", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def normalize_url(value: str | None) -> str:
    if not value:
        return ""
    parts = urlsplit(value)
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_KEYS
    ]
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit(
        (parts.scheme.casefold(), parts.netloc.casefold(), path, urlencode(query), "")
    )


def extract_explicit_requisition(payload: object) -> tuple[str | None, str | None]:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized_key = str(key).replace("-", "_").casefold()
            if normalized_key in _REQUISITION_KEYS and isinstance(value, str | int):
                requisition = str(value).strip()
                if requisition:
                    return requisition, str(key)
        for value in payload.values():
            found, provenance = extract_explicit_requisition(value)
            if found:
                return found, provenance
    elif isinstance(payload, list):
        for value in payload:
            found, provenance = extract_explicit_requisition(value)
            if found:
                return found, provenance
    return None, None


def explicit_redirect_target(payload: object) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    value = payload.get("redirect_target")
    return normalize_url(value) if isinstance(value, str) else None
