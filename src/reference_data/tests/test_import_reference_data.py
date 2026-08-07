from __future__ import annotations

from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from reference_data.importers import ReferenceDataError, read_csv_rows
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
        assert Municipality.objects.get(bfs_code=4001).municipality_name == "Gemeinde/Stadt Aarau"
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
