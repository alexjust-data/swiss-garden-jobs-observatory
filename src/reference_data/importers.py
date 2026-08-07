from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction

from reference_data.models import (
    CityPortalAudit,
    Municipality,
    PremiumSignal,
    PublicEmployer,
    RoleSearchTerm,
    SalaryReference,
)
from sources.models import Source

SNAPSHOT_DATE = date(2026, 1, 1)

EMPLOYER_HEADERS = (
    "universe_id",
    "employer_level",
    "country_code",
    "canton_code",
    "canton_name",
    "bfs_code",
    "employer_name",
    "district",
    "bfs_language_region_code",
    "language_region",
    "statistical_city",
    "degurb2021",
    "priority_tier",
    "expected_green_service_units",
    "canonical_portal_status",
    "canonical_portal_url",
    "portal_platform",
    "verification_status",
    "notes",
)
SOURCE_HEADERS = (
    "source_id",
    "source_name",
    "domain",
    "source_family",
    "source_type",
    "priority",
    "coverage_scope",
    "canonicality",
    "platform_family",
    "access_method",
    "automation_status",
    "legal_review_status",
    "verification_status",
    "official_url",
    "search_url",
    "notes",
)
ROLE_HEADERS = (
    "term_id",
    "canonical_role_family",
    "canonical_specialization",
    "search_term_de",
    "term_type",
    "include_default",
    "public_relevance",
    "default_access_level_hint",
    "notes",
)
PREMIUM_HEADERS = (
    "signal_id",
    "signal_group",
    "search_term",
    "evidence_scope",
    "base_weight",
    "default_segment",
    "notes",
)
SALARY_HEADERS = (
    "reference_id",
    "reference_type",
    "reference_scope",
    "qualification_level",
    "currency",
    "gross_net",
    "amount_monthly",
    "payments_per_year",
    "amount_annual",
    "amount_hourly_base",
    "valid_from",
    "valid_to",
    "applicability",
    "source_tier",
    "source_url",
    "notes",
)
CITY_HEADERS = (
    "queue_id",
    "priority",
    "canton_code",
    "bfs_code",
    "municipality",
    "district",
    "degurb2021",
    "canonical_portal_url",
    "platform_family",
    "portal_audit_status",
    "green_unit_hint",
    "search_query_1",
    "search_query_2",
    "acceptance_test",
)


class ReferenceDataError(ValueError):
    pass


@dataclass(frozen=True)
class ImportSummary:
    municipalities: int
    public_employers: int
    employment_sources: int
    salary_sources: int
    total_sources: int
    role_terms: int
    premium_signals: int
    salary_references: int
    city_audits: int


def read_csv_rows(
    path: Path,
    *,
    expected_headers: tuple[str, ...],
    expected_count: int,
    key_field: str,
) -> list[dict[str, str]]:
    if not path.is_file():
        raise ReferenceDataError(f"Missing reference file: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual_headers = tuple(reader.fieldnames or ())
        if actual_headers != expected_headers:
            raise ReferenceDataError(
                f"{path.name}: unexpected headers {actual_headers}; expected {expected_headers}"
            )
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    if len(rows) != expected_count:
        raise ReferenceDataError(f"{path.name}: expected {expected_count} rows, found {len(rows)}")

    keys = [row[key_field] for row in rows]
    if any(not key for key in keys):
        raise ReferenceDataError(f"{path.name}: empty {key_field}")
    if len(set(keys)) != len(keys):
        raise ReferenceDataError(f"{path.name}: duplicate {key_field}")
    return rows


def _required_int(value: str, *, field: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ReferenceDataError(f"{field}: expected integer, found {value!r}") from exc


def _optional_int(value: str, *, field: str) -> int | None:
    if not value or value == "UNKNOWN":
        return None
    return _required_int(value, field=field)


def _optional_decimal(value: str, *, field: str) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ReferenceDataError(f"{field}: expected decimal, found {value!r}") from exc


def _required_decimal(value: str, *, field: str) -> Decimal:
    parsed = _optional_decimal(value, field=field)
    if parsed is None:
        raise ReferenceDataError(f"{field}: decimal value is required")
    return parsed


def _decimal_range(value: str, *, field: str) -> tuple[str, Decimal | None, Decimal | None]:
    if not value:
        return "", None, None

    parts = value.split("-")
    if len(parts) > 2:
        raise ReferenceDataError(f"{field}: invalid range {value!r}")

    parsed = [_required_decimal(part.strip(), field=field) for part in parts]
    minimum = parsed[0]
    maximum = parsed[-1]
    if minimum < 0 or maximum < minimum:
        raise ReferenceDataError(f"{field}: invalid range {value!r}")
    return value, minimum, maximum


def _optional_date(value: str, *, field: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ReferenceDataError(f"{field}: expected ISO date, found {value!r}") from exc


def _required_bool(value: str, *, field: str) -> bool:
    if value == "YES":
        return True
    if value == "NO":
        return False
    raise ReferenceDataError(f"{field}: expected YES or NO, found {value!r}")


class ReferenceDataImporter:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir.resolve()

    def _file(self, name: str) -> Path:
        path = (self.data_dir / name).resolve()
        if not path.is_relative_to(self.data_dir):
            raise ReferenceDataError(f"Reference path escapes data directory: {name}")
        return path

    def _load(self) -> dict[str, list[dict[str, str]]]:
        datasets = {
            "employers": read_csv_rows(
                self._file("public_employer_universe_1397.csv"),
                expected_headers=EMPLOYER_HEADERS,
                expected_count=1397,
                key_field="universe_id",
            ),
            "sources": read_csv_rows(
                self._file("source_registry.csv"),
                expected_headers=SOURCE_HEADERS,
                expected_count=65,
                key_field="source_id",
            ),
            "roles": read_csv_rows(
                self._file("role_search_taxonomy.csv"),
                expected_headers=ROLE_HEADERS,
                expected_count=53,
                key_field="term_id",
            ),
            "premium": read_csv_rows(
                self._file("premium_signal_taxonomy.csv"),
                expected_headers=PREMIUM_HEADERS,
                expected_count=26,
                key_field="signal_id",
            ),
            "salary": read_csv_rows(
                self._file("salary_reference_2026.csv"),
                expected_headers=SALARY_HEADERS,
                expected_count=12,
                key_field="reference_id",
            ),
            "cities": read_csv_rows(
                self._file("city_portal_audit_queue_127.csv"),
                expected_headers=CITY_HEADERS,
                expected_count=127,
                key_field="queue_id",
            ),
        }
        self._validate_cross_dataset_contracts(datasets)
        return datasets

    def _validate_cross_dataset_contracts(self, datasets: dict[str, list[dict[str, str]]]) -> None:
        employers = datasets["employers"]
        municipalities = [row for row in employers if row["employer_level"] == "MUNICIPALITY"]
        cantons = [row for row in employers if row["employer_level"] == "CANTON"]
        federal = [row for row in employers if row["employer_level"] == "FEDERAL"]

        if (len(municipalities), len(cantons), len(federal)) != (1374, 22, 1):
            raise ReferenceDataError(
                "public employer split must be 1374 municipalities, 22 cantons and 1 federal"
            )
        if any(row["language_region"] != "GERMAN" for row in municipalities):
            raise ReferenceDataError("all imported municipalities must be in the GERMAN region")

        municipality_bfs = {row["bfs_code"] for row in municipalities}
        if len(municipality_bfs) != 1374 or "" in municipality_bfs:
            raise ReferenceDataError("municipality BFS codes must be present and unique")

        statistical_city_bfs = {
            row["bfs_code"] for row in municipalities if row["statistical_city"] == "YES"
        }
        city_queue_bfs = {row["bfs_code"] for row in datasets["cities"]}
        if len(statistical_city_bfs) != 127 or city_queue_bfs != statistical_city_bfs:
            raise ReferenceDataError(
                "city audit queue must match the 127 BFS statistical cities exactly"
            )

        salary_sources = [
            row for row in datasets["sources"] if row["source_family"] == "SALARY_REFERENCE"
        ]
        if len(salary_sources) != 4 or len(datasets["sources"]) - len(salary_sources) != 61:
            raise ReferenceDataError(
                "source registry must contain 61 employment sources and 4 salary sources"
            )

    @transaction.atomic
    def run(self) -> ImportSummary:
        datasets = self._load()
        self._import_sources(datasets["sources"])
        self._import_municipalities(datasets["employers"])
        self._import_public_employers(datasets["employers"])
        self._import_city_audits(datasets["cities"])
        self._import_roles(datasets["roles"])
        self._import_premium_signals(datasets["premium"])
        self._import_salary_references(datasets["salary"])

        summary = self.summary()
        expected = ImportSummary(1374, 1397, 61, 4, 65, 53, 26, 12, 127)
        if summary != expected:
            raise ReferenceDataError(
                f"database counts do not match the frozen v0.4 contract: {summary}"
            )
        return summary

    def _import_sources(self, rows: list[dict[str, str]]) -> None:
        objects = [
            Source(
                source_id=row["source_id"],
                source_name=row["source_name"],
                domain=row["domain"],
                source_family=row["source_family"],
                source_type=row["source_type"],
                priority=row["priority"],
                coverage_scope=row["coverage_scope"],
                canonicality=row["canonicality"],
                platform_family=row["platform_family"],
                access_method=row["access_method"],
                automation_status=row["automation_status"],
                legal_review_status=row["legal_review_status"],
                verification_status=row["verification_status"],
                official_url=row["official_url"],
                search_url=row["search_url"],
                notes=row["notes"],
            )
            for row in rows
        ]
        Source.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=["source_id"],
            update_fields=[
                "source_name",
                "domain",
                "source_family",
                "source_type",
                "priority",
                "coverage_scope",
                "canonicality",
                "platform_family",
                "access_method",
                "automation_status",
                "legal_review_status",
                "verification_status",
                "official_url",
                "search_url",
                "notes",
            ],
        )

    def _municipality_rows(self, rows: list[dict[str, str]]) -> list[dict[str, str]]:
        return [row for row in rows if row["employer_level"] == "MUNICIPALITY"]

    def _import_municipalities(self, rows: list[dict[str, str]]) -> None:
        objects = [
            Municipality(
                bfs_code=_required_int(row["bfs_code"], field="bfs_code"),
                snapshot_date=SNAPSHOT_DATE,
                municipality_name=row["employer_name"],
                canton_code=row["canton_code"],
                canton_name=row["canton_name"],
                district=row["district"],
                bfs_language_region_code=_required_int(
                    row["bfs_language_region_code"], field="bfs_language_region_code"
                ),
                language_region=row["language_region"],
                statistical_city=_required_bool(row["statistical_city"], field="statistical_city"),
                degurb2021=_required_int(row["degurb2021"], field="degurb2021"),
                priority_tier=row["priority_tier"],
            )
            for row in self._municipality_rows(rows)
        ]
        Municipality.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=["bfs_code"],
            update_fields=[
                "snapshot_date",
                "municipality_name",
                "canton_code",
                "canton_name",
                "district",
                "bfs_language_region_code",
                "language_region",
                "statistical_city",
                "degurb2021",
                "priority_tier",
            ],
        )

    def _import_public_employers(self, rows: list[dict[str, str]]) -> None:
        objects = [
            PublicEmployer(
                universe_id=row["universe_id"],
                employer_level=row["employer_level"],
                country_code=row["country_code"],
                canton_code=row["canton_code"],
                canton_name=row["canton_name"],
                employer_name=row["employer_name"],
                municipality_id=(
                    _required_int(row["bfs_code"], field="bfs_code") if row["bfs_code"] else None
                ),
                language_region=row["language_region"],
                priority_tier=row["priority_tier"],
                expected_green_service_units=row["expected_green_service_units"],
                canonical_portal_status=row["canonical_portal_status"],
                canonical_portal_url=row["canonical_portal_url"],
                portal_platform=row["portal_platform"],
                verification_status=row["verification_status"],
                notes=row["notes"],
            )
            for row in rows
        ]
        PublicEmployer.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=["universe_id"],
            update_fields=[
                "employer_level",
                "country_code",
                "canton_code",
                "canton_name",
                "employer_name",
                "municipality",
                "language_region",
                "priority_tier",
                "expected_green_service_units",
                "canonical_portal_status",
                "canonical_portal_url",
                "portal_platform",
                "verification_status",
                "notes",
            ],
        )

    def _import_city_audits(self, rows: list[dict[str, str]]) -> None:
        objects = [
            CityPortalAudit(
                queue_id=row["queue_id"],
                municipality_id=_required_int(row["bfs_code"], field="bfs_code"),
                priority=row["priority"],
                canton_code=row["canton_code"],
                municipality_name=row["municipality"],
                district=row["district"],
                degurb2021=_required_int(row["degurb2021"], field="degurb2021"),
                canonical_portal_url=row["canonical_portal_url"],
                platform_family=row["platform_family"],
                portal_audit_status=row["portal_audit_status"],
                green_unit_hint=row["green_unit_hint"],
                search_query_1=row["search_query_1"],
                search_query_2=row["search_query_2"],
                acceptance_test=row["acceptance_test"],
            )
            for row in rows
        ]
        CityPortalAudit.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=["queue_id"],
            update_fields=[
                "municipality",
                "priority",
                "canton_code",
                "municipality_name",
                "district",
                "degurb2021",
                "canonical_portal_url",
                "platform_family",
                "portal_audit_status",
                "green_unit_hint",
                "search_query_1",
                "search_query_2",
                "acceptance_test",
            ],
        )

    def _import_roles(self, rows: list[dict[str, str]]) -> None:
        objects = [
            RoleSearchTerm(
                term_id=row["term_id"],
                canonical_role_family=row["canonical_role_family"],
                canonical_specialization=row["canonical_specialization"],
                search_term_de=row["search_term_de"],
                term_type=row["term_type"],
                include_default=row["include_default"],
                public_relevance=row["public_relevance"],
                default_access_level_hint=row["default_access_level_hint"],
                notes=row["notes"],
            )
            for row in rows
        ]
        RoleSearchTerm.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=["term_id"],
            update_fields=[
                "canonical_role_family",
                "canonical_specialization",
                "search_term_de",
                "term_type",
                "include_default",
                "public_relevance",
                "default_access_level_hint",
                "notes",
            ],
        )

    def _import_premium_signals(self, rows: list[dict[str, str]]) -> None:
        objects = [
            PremiumSignal(
                signal_id=row["signal_id"],
                signal_group=row["signal_group"],
                search_term=row["search_term"],
                evidence_scope=row["evidence_scope"],
                base_weight=_required_decimal(row["base_weight"], field="base_weight"),
                default_segment=row["default_segment"],
                notes=row["notes"],
            )
            for row in rows
        ]
        PremiumSignal.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=["signal_id"],
            update_fields=[
                "signal_group",
                "search_term",
                "evidence_scope",
                "base_weight",
                "default_segment",
                "notes",
            ],
        )

    def _import_salary_references(self, rows: list[dict[str, str]]) -> None:
        objects: list[SalaryReference] = []
        for row in rows:
            monthly_raw, monthly_min, monthly_max = _decimal_range(
                row["amount_monthly"], field="amount_monthly"
            )
            annual_raw, annual_min, annual_max = _decimal_range(
                row["amount_annual"], field="amount_annual"
            )
            hourly_raw, hourly_min, hourly_max = _decimal_range(
                row["amount_hourly_base"], field="amount_hourly_base"
            )
            objects.append(
                SalaryReference(
                    reference_id=row["reference_id"],
                    reference_type=row["reference_type"],
                    reference_scope=row["reference_scope"],
                    qualification_level=row["qualification_level"],
                    currency=row["currency"],
                    gross_net=row["gross_net"],
                    amount_monthly_raw=monthly_raw,
                    amount_monthly_min=monthly_min,
                    amount_monthly_max=monthly_max,
                    payments_per_year=_optional_int(
                        row["payments_per_year"], field="payments_per_year"
                    ),
                    amount_annual_raw=annual_raw,
                    amount_annual_min=annual_min,
                    amount_annual_max=annual_max,
                    amount_hourly_base_raw=hourly_raw,
                    amount_hourly_base_min=hourly_min,
                    amount_hourly_base_max=hourly_max,
                    valid_from=_optional_date(row["valid_from"], field="valid_from"),
                    valid_to=_optional_date(row["valid_to"], field="valid_to"),
                    applicability=row["applicability"],
                    source_tier=row["source_tier"],
                    source_url=row["source_url"],
                    notes=row["notes"],
                )
            )

        SalaryReference.objects.bulk_create(
            objects,
            update_conflicts=True,
            unique_fields=["reference_id"],
            update_fields=[
                "reference_type",
                "reference_scope",
                "qualification_level",
                "currency",
                "gross_net",
                "amount_monthly_raw",
                "amount_monthly_min",
                "amount_monthly_max",
                "payments_per_year",
                "amount_annual_raw",
                "amount_annual_min",
                "amount_annual_max",
                "amount_hourly_base_raw",
                "amount_hourly_base_min",
                "amount_hourly_base_max",
                "valid_from",
                "valid_to",
                "applicability",
                "source_tier",
                "source_url",
                "notes",
            ],
        )

    @staticmethod
    def summary() -> ImportSummary:
        salary_sources = Source.objects.filter(source_family="SALARY_REFERENCE").count()
        total_sources = Source.objects.count()
        return ImportSummary(
            municipalities=Municipality.objects.count(),
            public_employers=PublicEmployer.objects.count(),
            employment_sources=total_sources - salary_sources,
            salary_sources=salary_sources,
            total_sources=total_sources,
            role_terms=RoleSearchTerm.objects.count(),
            premium_signals=PremiumSignal.objects.count(),
            salary_references=SalaryReference.objects.count(),
            city_audits=CityPortalAudit.objects.count(),
        )
