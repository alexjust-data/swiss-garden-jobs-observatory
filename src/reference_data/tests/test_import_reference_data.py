from __future__ import annotations

from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from reference_data.importers import (
    ReferenceDataError,
    ReferenceDataImporter,
    _canonical_municipality_name,
    _positive_optional_int,
    _premium_weight,
    _validated_date_range,
    read_csv_rows,
)
from reference_data.models import (
    CityPortalAudit,
    Municipality,
    PremiumSignal,
    PublicEmployer,
    RoleSearchTerm,
    SalaryReference,
)
from sources.models import Source


class ReferenceDataImportTests(TestCase):
    def test_import_reference_data_is_complete_and_idempotent(self) -> None:
        output = StringIO()
        call_command("import_reference_data", stdout=output)

        assert Municipality.objects.count() == 1374
        assert Municipality.objects.filter(statistical_city=True).count() == 127
        assert PublicEmployer.objects.count() == 1397
        assert PublicEmployer.objects.filter(employer_level="CANTON").count() == 22
        assert PublicEmployer.objects.filter(employer_level="FEDERAL").count() == 1
        assert Source.objects.count() == 65
        assert Source.objects.exclude(source_family="SALARY_REFERENCE").count() == 61
        assert Source.objects.filter(source_family="SALARY_REFERENCE").count() == 4
        assert RoleSearchTerm.objects.count() == 53
        assert PremiumSignal.objects.count() == 26
        assert SalaryReference.objects.count() == 12
        zurich = SalaryReference.objects.get(
            reference_id="SALREF-PUBLIC-ZURICH-GARDENER-REF50017-2026"
        )
        assert zurich.amount_annual_raw == "70000-82000"
        assert zurich.amount_annual_min == Decimal("70000")
        assert zurich.amount_annual_max == Decimal("82000")
        assert CityPortalAudit.objects.count() == 127

        municipality = Municipality.objects.get(bfs_code=4001)
        municipality.municipality_name = "tampered"
        municipality.save(update_fields=["municipality_name"])

        call_command("import_reference_data", stdout=StringIO())

        assert Municipality.objects.count() == 1374
        municipality = Municipality.objects.get(bfs_code=4001)
        assert municipality.municipality_name == "Aarau"
        public_employer = PublicEmployer.objects.get(municipality_id=4001)
        assert public_employer.employer_name == "Gemeinde/Stadt Aarau"
        assert "Total source registry rows: 65" in output.getvalue()


def test_read_csv_rows_rejects_duplicate_keys(tmp_path: Path) -> None:
    csv_file = tmp_path / "duplicate.csv"
    csv_file.write_text("id,name\nA,first\nA,second\n", encoding="utf-8")

    with pytest.raises(ReferenceDataError, match="duplicate id"):
        read_csv_rows(
            csv_file,
            expected_headers=("id", "name"),
            expected_count=2,
            key_field="id",
        )


def test_frozen_reference_files_are_not_salary_observations() -> None:
    data_dir = Path(settings.BASE_DIR) / "docs" / "research" / "v0_4"

    assert (data_dir / "salary_reference_2026.csv").is_file()
    assert (data_dir / "salary_evidence_seed_2026-08-07.csv").is_file()
    assert "salary_evidence_seed_2026-08-07.csv" not in {
        "public_employer_universe_1397.csv",
        "source_registry.csv",
        "role_search_taxonomy.csv",
        "premium_signal_taxonomy.csv",
        "salary_reference_2026.csv",
        "city_portal_audit_queue_127.csv",
    }


def test_municipality_name_normalization_is_strict() -> None:
    assert _canonical_municipality_name("Gemeinde/Stadt Aarau") == "Aarau"
    assert _canonical_municipality_name("Gemeinde/Stadt Arni (AG)") == "Arni (AG)"

    with pytest.raises(ReferenceDataError, match="must start with"):
        _canonical_municipality_name("Stadt Aarau")


@pytest.mark.parametrize(
    ("city_field", "invalid_value"),
    [
        ("canton_code", "ZZ"),
        ("municipality", "Not Aarau"),
        ("degurb2021", "3"),
    ],
)
def test_city_audit_metadata_must_match_municipality(city_field: str, invalid_value: str) -> None:
    data_dir = Path(settings.BASE_DIR) / "docs" / "research" / "v0_4"
    importer = ReferenceDataImporter(data_dir)
    datasets = importer._load()
    datasets["cities"][0][city_field] = invalid_value

    with pytest.raises(ReferenceDataError, match="city audit contract mismatch"):
        importer._validate_cross_dataset_contracts(datasets)


def test_city_audit_requires_statistical_city() -> None:
    data_dir = Path(settings.BASE_DIR) / "docs" / "research" / "v0_4"
    importer = ReferenceDataImporter(data_dir)
    datasets = importer._load()
    bfs_code = datasets["cities"][0]["bfs_code"]
    municipality = next(row for row in datasets["employers"] if row["bfs_code"] == bfs_code)
    municipality["statistical_city"] = "NO"

    with pytest.raises(ReferenceDataError, match="127 BFS statistical cities"):
        importer._validate_cross_dataset_contracts(datasets)


def test_reference_value_invariants() -> None:
    assert _premium_weight("0") == Decimal("0")
    assert _premium_weight("1") == Decimal("1")
    with pytest.raises(ReferenceDataError, match="between 0 and 1"):
        _premium_weight("1.01")

    assert _positive_optional_int("13", field="payments_per_year") == 13
    with pytest.raises(ReferenceDataError, match="positive integer"):
        _positive_optional_int("0", field="payments_per_year")

    with pytest.raises(ReferenceDataError, match="valid_to"):
        _validated_date_range("2026-12-31", "2026-01-01")
