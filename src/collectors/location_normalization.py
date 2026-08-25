from __future__ import annotations

import re
import unicodedata

from reference_data.models import Municipality

_COUNTRY_ALIASES = frozenset(
    {
        "ch",
        "che",
        "schweiz",
        "suisse",
        "svizzera",
        "switzerland",
    }
)

_CANTON_NAMES = {
    "aargau": "AG",
    "appenzell ausserrhoden": "AR",
    "appenzell innerrhoden": "AI",
    "basel landschaft": "BL",
    "basel stadt": "BS",
    "bern": "BE",
    "berne": "BE",
    "fribourg": "FR",
    "freiburg": "FR",
    "geneve": "GE",
    "genf": "GE",
    "glarus": "GL",
    "graubuenden": "GR",
    "grigioni": "GR",
    "grisons": "GR",
    "jura": "JU",
    "luzern": "LU",
    "lucerne": "LU",
    "neuchatel": "NE",
    "neuenburg": "NE",
    "nidwalden": "NW",
    "obwalden": "OW",
    "schaffhausen": "SH",
    "schwyz": "SZ",
    "solothurn": "SO",
    "st gallen": "SG",
    "thurgau": "TG",
    "ticino": "TI",
    "tessin": "TI",
    "uri": "UR",
    "vaud": "VD",
    "waadt": "VD",
    "valais": "VS",
    "wallis": "VS",
    "zug": "ZG",
    "zuerich": "ZH",
}
_CANTON_CODES = frozenset(_CANTON_NAMES.values())


def swiss_place_key(value: str) -> str:
    """Return an exact, punctuation-insensitive Swiss place-name key."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = (
        normalized.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def canonical_swiss_country(value: str) -> str:
    stripped = " ".join(value.split())
    if not stripped:
        return ""
    return "CH" if swiss_place_key(stripped) in _COUNTRY_ALIASES else stripped.upper()


def canonical_canton_code(value: str) -> str:
    stripped = " ".join(value.split())
    upper = stripped.upper()
    if upper in _CANTON_CODES:
        return upper
    return _CANTON_NAMES.get(swiss_place_key(stripped), "")

def resolve_swiss_municipality(
    locality: str,
    region: str = "",
    *,
    fallback_canton: str = "",
) -> Municipality | None:
    locality_key = swiss_place_key(locality)
    if not locality_key:
        return None
    canton_code = canonical_canton_code(region) or canonical_canton_code(fallback_canton)
    candidates = Municipality.objects.all()
    if canton_code:
        candidates = candidates.filter(canton_code=canton_code)
    exact_matches = list(
        candidates.filter(municipality_name__iexact=locality.strip()).only(
            "bfs_code", "municipality_name", "canton_code"
        )[:2]
    )
    if len(exact_matches) == 1:
        return exact_matches[0]
    matches = [
        municipality
        for municipality in candidates.only("bfs_code", "municipality_name", "canton_code")
        if swiss_place_key(municipality.municipality_name) == locality_key
    ][:2]
    return matches[0] if len(matches) == 1 else None
