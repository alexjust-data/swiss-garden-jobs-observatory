from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from django.db.models import Model


def canonical_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("naive datetime is not canonical authority evidence")
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID | Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [canonical_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(canonical_value(value), sort_keys=True, separators=(",", ":"))


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def row_hash_inventory(rows: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    return {
        category: [str(row["row_sha256"]) for row in values]
        for category, values in sorted(rows.items())
    }


def relationship_graph(
    rows: dict[str, list[dict[str, Any]]], model_map: dict[str, type[Model]]
) -> list[dict[str, Any]]:
    included = {
        (str(row["model"]), str(row["pk"]))
        for values in rows.values()
        for row in values
    }
    edges: list[dict[str, Any]] = []
    for values in rows.values():
        for row in values:
            model_name = str(row["model"])
            model = model_map.get(model_name)
            fields = row.get("fields")
            if model is None or not isinstance(fields, dict):
                continue
            for field in model._meta.fields:
                if not field.is_relation or field.attname not in fields:
                    continue
                target_pk = fields[field.attname]
                related_model = field.related_model
                if target_pk is None or related_model is None:
                    continue
                target_model = cast(Any, related_model)._meta.label_lower
                edges.append(
                    {
                        "source_model": model_name,
                        "source_pk": str(row["pk"]),
                        "field": field.attname,
                        "target_model": target_model,
                        "target_pk": str(target_pk),
                        "target_included_in_package": (target_model, str(target_pk)) in included,
                    }
                )
            if model_name == "vacancies.dedupdecision":
                evidence = fields.get("evidence")
                algorithm_id = (
                    evidence.get("algorithm_decision_id")
                    if isinstance(evidence, dict)
                    else None
                )
                if algorithm_id:
                    edges.append(
                        {
                            "source_model": model_name,
                            "source_pk": str(row["pk"]),
                            "field": "evidence.algorithm_decision_id",
                            "target_model": "vacancies.dedupdecision",
                            "target_pk": str(algorithm_id),
                            "target_included_in_package": (
                                "vacancies.dedupdecision",
                                str(algorithm_id),
                            )
                            in included,
                        }
                    )
    return sorted(
        edges,
        key=lambda edge: (
            edge["source_model"],
            edge["source_pk"],
            edge["field"],
            edge["target_model"],
            edge["target_pk"],
        ),
    )


def source_snapshot_fingerprint(
    metadata: dict[str, Any],
    row_inventory: dict[str, list[str]],
    graph: list[dict[str, Any]],
) -> str:
    return sha256(
        {
            "source_snapshot_metadata": metadata,
            "row_hash_inventory": row_inventory,
            "relationship_graph": graph,
        }
    )
