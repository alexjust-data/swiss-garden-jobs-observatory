from __future__ import annotations

import re
import unicodedata

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
        normalized.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
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
        return "CH"
    return "CH" if swiss_place_key(stripped) in _COUNTRY_ALIASES else stripped.upper()


def canonical_canton_code(value: str) -> str:
    stripped = " ".join(value.split())
    upper = stripped.upper()
    if upper in _CANTON_CODES:
        return upper
    return _CANTON_NAMES.get(swiss_place_key(stripped), "")
