from __future__ import annotations

from datetime import date

import pytest
from django.test import TestCase

from collectors.location_normalization import (
    canonical_canton_code,
    canonical_swiss_country,
    swiss_place_key,
)
from collectors.pipeline import resolve_municipality
from collectors.platforms import ParsedSourcePosting
from reference_data.models import Municipality


@pytest.mark.parametrize(
    "value",
    ["CH", "CHE", "Schweiz", "Suisse", "Svizzera", "Switzerland"],
)
def test_canonical_swiss_country_aliases(value: str) -> None:
    assert canonical_swiss_country(value) == "CH"


@pytest.mark.parametrize("value", ["", " ", "\t", "\n"])
def test_blank_country_remains_unknown(value: str) -> None:
    assert canonical_swiss_country(value) == ""


def test_unknown_country_is_not_silently_reclassified() -> None:
    assert canonical_swiss_country("Deutschland") == "DEUTSCHLAND"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ZH", "ZH"),
        ("Zürich", "ZH"),
        ("Graubünden", "GR"),
        ("Genève", "GE"),
        ("St. Gallen", "SG"),
        ("DE", ""),
        ("Bern / Solothurn", ""),
    ],
)
def test_canonical_canton_code_is_exact(value: str, expected: str) -> None:
    assert canonical_canton_code(value) == expected


def test_swiss_place_key_handles_governed_spelling_variants() -> None:
    assert swiss_place_key("Zürich") == swiss_place_key("Zuerich")
    assert swiss_place_key("St.Gallen") == swiss_place_key("St. Gallen")


class MunicipalityResolutionTests(TestCase):
    @staticmethod
    def municipality(
        *, bfs_code: int, name: str, canton_code: str, canton_name: str
    ) -> Municipality:
        return Municipality.objects.create(
            bfs_code=bfs_code,
            snapshot_date=date(2026, 1, 1),
            municipality_name=name,
            canton_code=canton_code,
            canton_name=canton_name,
            district="",
            bfs_language_region_code=1,
            language_region="GERMAN",
            statistical_city=False,
            degurb2021=3,
            priority_tier="NONE",
        )

    @staticmethod
    def parsed(locality: str, region: str) -> ParsedSourcePosting:
        return ParsedSourcePosting(
            source_posting_id="posting-1",
            canonical_url="https://example.invalid/jobs/posting-1",
            title="Gärtner/in",
            published_at_raw=None,
            date_posted=None,
            valid_through=None,
            employment_type="",
            hiring_organization="",
            description_html="",
            responsibilities_html="",
            qualifications_html="",
            benefits_html="",
            raw_location=locality,
            location_street="",
            location_locality=locality,
            location_region=region,
            location_postal_code="",
            location_country="CH",
            structured_payload={},
        )

    def test_transliteration_and_canton_code_resolve_exactly(self) -> None:
        zurich = self.municipality(
            bfs_code=261, name="Zürich", canton_code="ZH", canton_name="Zürich"
        )
        assert resolve_municipality(self.parsed("Zuerich", "ZH")) == zurich

    def test_punctuation_and_canton_name_resolve_exactly(self) -> None:
        st_gallen = self.municipality(
            bfs_code=3203,
            name="St. Gallen",
            canton_code="SG",
            canton_name="St. Gallen",
        )
        assert resolve_municipality(self.parsed("St.Gallen", "St. Gallen")) == st_gallen

    def test_canton_name_and_unique_locality_are_supported(self) -> None:
        bern = self.municipality(bfs_code=351, name="Bern", canton_code="BE", canton_name="Bern")
        solothurn = self.municipality(
            bfs_code=2601,
            name="Solothurn",
            canton_code="SO",
            canton_name="Solothurn",
        )
        assert resolve_municipality(self.parsed("Bern", "Bern")) == bern
        assert resolve_municipality(self.parsed("Solothurn", "Bern / Solothurn")) == solothurn

    def test_ambiguous_locality_requires_a_governed_canton(self) -> None:
        bern_rüti = self.municipality(
            bfs_code=861, name="Rüti", canton_code="BE", canton_name="Bern"
        )
        zurich_rüti = self.municipality(
            bfs_code=118,
            name="Rüti",
            canton_code="ZH",
            canton_name="Zürich",
        )
        assert resolve_municipality(self.parsed("Rueti", "")) is None
        assert resolve_municipality(self.parsed("Rueti", "Bern")) == bern_rüti
        assert resolve_municipality(self.parsed("Rueti", "ZH")) == zurich_rüti
