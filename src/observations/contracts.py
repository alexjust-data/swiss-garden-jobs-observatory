from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast

from django.conf import settings
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = (
    Path(settings.BASE_DIR) / "docs" / "research" / "v0_4" / "posting_observation_v1_2.schema.json"
)


class PostingObservationContractError(ValueError):
    pass


@lru_cache(maxsize=1)
def posting_observation_validator() -> Draft202012Validator:
    schema = cast(dict[str, object], json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_posting_observation_contract(payload: dict[str, object]) -> None:
    errors = sorted(
        posting_observation_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return
    details = "; ".join(
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    )
    raise PostingObservationContractError(f"posting_observation_v1_2 validation failed: {details}")
