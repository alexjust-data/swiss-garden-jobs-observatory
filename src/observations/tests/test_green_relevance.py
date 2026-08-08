from __future__ import annotations

from copy import deepcopy
from tempfile import TemporaryDirectory

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from collectors.winterthur import (
    WINTERTHUR_LISTING_URL,
    FetchedPage,
    WinterthurCollector,
    WinterthurCollectorError,
)
from core.hashing import sha256_file
from core.storage import RawObjectStore
from observations.green_relevance import TAXONOMY_PATH, GreenRelevanceClassifier
from observations.models import (
    CollectionRun,
    GreenRelevanceAssessment,
    ImmutableGreenRelevanceAssessmentError,
    PostingObservation,
)
from observations.tests.test_winterthur_collector import (
    LISTING,
    FakeFetcher,
    WinterthurCollectorTests,
    fake_fetcher,
)


@pytest.mark.parametrize(
    ("title", "text", "org", "expected"),
    [
        ("G\u00e4rtner:in Gartenunterhalt", "", "", "GREEN_CONFIRMED"),
        ("Landschaftsg\u00e4rtner", "", "", "GREEN_CONFIRMED"),
        ("Mitarbeiter Werkhof", "", "", "REVIEW"),
        ("Mitarbeiter Werkhof", "Gr\u00fcnpflege", "", "GREEN_CONFIRMED"),
        ("Fachmann Betriebsunterhalt", "Arealpflege", "", "GREEN_CONFIRMED"),
        ("Winterdienst", "", "", "REVIEW"),
        ("Softwareentwickler", "Cloud-Plattform", "IT", "NOT_GREEN"),
        ("Reinigung", "", "", "NOT_GREEN"),
        ("Reinigung", "Gr\u00fcnpflege", "", "REVIEW"),
        ("Sachbearbeiter", "Budget und Termine", "Stadtgr\u00fcn", "REVIEW"),
    ],
)
def test_rules(title: str, text: str, org: str, expected: str) -> None:
    assert (
        GreenRelevanceClassifier().classify(title=title, text=text, organization=org).result
        == expected
    )


def test_deterministic_and_taxonomy_sha() -> None:
    classifier = GreenRelevanceClassifier()
    args = {"title": "G?RTNER:IN  Gartenunterhalt", "text": "", "organization": ""}
    assert classifier.classify(**args) == classifier.classify(**args)
    assert classifier.taxonomy_sha256 == sha256_file(TAXONOMY_PATH)


class Gate004PersistenceTests(WinterthurCollectorTests):
    def test_targeted_is_never_complete_and_assessment_is_separate_append_only(self) -> None:
        with TemporaryDirectory() as raw_dir:
            run = self.collect_once(raw_dir)
            observation = PostingObservation.objects.get()
            original_contract = deepcopy(observation.contract_payload)
            assessment = GreenRelevanceAssessment.objects.get()
            assert run.run_scope == CollectionRun.RunScope.TARGETED
            assert run.snapshot_complete is False
            assert observation.contract_payload == original_contract
            assessment.result = "NOT_GREEN"
            with pytest.raises(ImmutableGreenRelevanceAssessmentError):
                assessment.save()
            with pytest.raises(ImmutableGreenRelevanceAssessmentError):
                GreenRelevanceAssessment.objects.filter(pk=assessment.pk).update(result="NOT_GREEN")
            with pytest.raises(ImmutableGreenRelevanceAssessmentError):
                GreenRelevanceAssessment.objects.filter(pk=assessment.pk).delete()
            with pytest.raises(ImmutableGreenRelevanceAssessmentError):
                GreenRelevanceAssessment.objects.bulk_update([assessment], ["result"])
            observation.refresh_from_db()
            assert observation.contract_payload == original_contract

    def test_full_snapshot_has_equal_counts_and_sets(self) -> None:
        with TemporaryDirectory() as raw_dir:
            run = WinterthurCollector(
                fetcher=fake_fetcher(), raw_store=RawObjectStore(raw_dir), delay_seconds=0
            ).collect(full_snapshot=True, acknowledge_automation_review=True)
            listing_ids = {"8280"}
            observation_ids = set(
                PostingObservation.objects.filter(collection_run=run).values_list(
                    "source_posting_id", flat=True
                )
            )
            assessment_ids = set(
                PostingObservation.objects.filter(
                    collection_run=run, green_relevance_assessments__isnull=False
                ).values_list("source_posting_id", flat=True)
            )
            assert listing_ids == observation_ids == assessment_ids
            assert (
                run.listings_discovered
                == run.details_fetched
                == run.observations_created
                == run.green_assessments_created
                == 1
            )
            assert run.snapshot_complete is True

    def test_failed_detail_preserves_previous_evidence(self) -> None:
        second_url = "https://jobs.winterthur.ch/?yid=8281"
        listing = LISTING + b'<a href="https://jobs.winterthur.ch/?yid=8281">Second</a>'
        pages = fake_fetcher().pages
        pages[WINTERTHUR_LISTING_URL] = FetchedPage(
            WINTERTHUR_LISTING_URL, WINTERTHUR_LISTING_URL, 200, "text/html", listing
        )
        pages[second_url] = FetchedPage(
            second_url, second_url, 200, "text/html", b"<html>invalid</html>"
        )
        with TemporaryDirectory() as raw_dir:
            collector = WinterthurCollector(
                fetcher=FakeFetcher(pages), raw_store=RawObjectStore(raw_dir), delay_seconds=0
            )
            with pytest.raises(WinterthurCollectorError):
                collector.collect(full_snapshot=True, acknowledge_automation_review=True)
            run = CollectionRun.objects.get()
            assert run.status == CollectionRun.Status.FAILED and run.snapshot_complete is False
            assert "posting 8281" in run.error_message
            assert (
                PostingObservation.objects.count() == GreenRelevanceAssessment.objects.count() == 1
            )


class Gate004CliTests(SimpleTestCase):
    def test_no_scope(self) -> None:
        with pytest.raises(CommandError):
            call_command("collect_winterthur")

    def test_full_with_posting(self) -> None:
        with pytest.raises(CommandError):
            call_command("collect_winterthur", "--full-snapshot", "--posting-id", "8280")

    def test_full_with_limit(self) -> None:
        with pytest.raises(CommandError):
            call_command("collect_winterthur", "--full-snapshot", "--limit", "1")
