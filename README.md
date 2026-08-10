# Swiss Garden Jobs Observatory

This repository contains the modular Django monolith for the Swiss Garden Jobs Observatory.

## Requirements

- Python 3.12
- Docker
- Git

## Quick start

```bash
cp .env.example .env
docker compose up -d --wait db

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

python manage.py migrate --noinput
python manage.py import_reference_data
python manage.py runserver 0.0.0.0:8000
```

In PowerShell, use `Copy-Item .env.example .env` instead of `cp`. Django running on the
host connects to PostgreSQL at `127.0.0.1:5432`. The values in `.env.example` are local-only
examples and must not be reused in a shared or production environment.

## GATE-002 reference data

`import_reference_data` validates the frozen v0.4 CSV headers, natural keys, row counts and
cross-dataset BFS relationships before performing atomic upserts. Re-running it updates existing
reference rows and does not create duplicates.

```text
German-speaking municipalities: 1374
Public employers: 1397
Employment sources: 61
Salary reference sources: 4
Total source registry rows: 65
Role taxonomy terms: 53
Premium signals: 26
Salary references: 12
City portal audits: 127
```

The source registry contains the 61 employment sources documented in
`02_MASTER_SOURCE_REGISTRY.md` plus four `SALARY_REFERENCE` rows introduced by the salary
contract. Salary reference rows remain separate from advertised salary observations.
`salary_evidence_seed_2026-08-07.csv` is not imported in GATE-002.

## Validation

```bash
make migrate
make import-reference-data
make test
make lint
make typecheck
```

Tests and migrations use PostgreSQL. Verify the active backend with:

```bash
python manage.py shell -c "from django.db import connection; connection.ensure_connection(); print(connection.vendor)"
```

The expected output is `postgresql`.

### Health endpoint

```bash
curl http://127.0.0.1:8000/api/health/
```

Expected response:

```json
{"status":"ok","service":"swiss-garden-jobs-observatory"}
```

## Implemented scope

- Django and Django REST Framework modular monolith.
- PostgreSQL-only runtime configuration.
- Immutable local RAW object storage with SHA-256 helpers.
- Health endpoint.
- Frozen v0.4 reference data import and validation.
- Django admin for sources and reference datasets.
- pytest, Ruff, mypy and GitHub Actions.

No collectors, scraping, vacancy ingestion, deduplication, salary observations, geocoding,
dashboard, scheduler or AI classification are implemented.

## GATE-003: manual Winterthur point-in-time collector

Winterthur is configured as `AUTOMATION_REVIEW_REQUIRED` in the frozen source registry. The collector is therefore manual, has no scheduler, identifies itself with a project User-Agent, stays on the `jobs.winterthur.ch` HTTPS origin, fetches sequentially, and requires explicit acknowledgement:

```bash
python manage.py collect_winterthur --full-snapshot --acknowledge-automation-review
```

For a controlled acceptance run, select an active source posting ID or limit the run:

```bash
python manage.py collect_winterthur \
  --posting-id 8280 \
  --delay-seconds 1 \
  --acknowledge-automation-review
```

Each run stores the exact listing and detail response bytes under `CORE_RAW_OBJECT_STORE_PATH`, verifies SHA-256 after writing, records `RawArtifact` metadata, and creates immutable `PostingObservation` rows with the original URL, publication dates, JSON-LD payload, and BFS municipality 230 (Winterthur).

This gate does not provide scheduling, vacancy deduplication, classification, geocoding, maps, dashboards, alerts, or multi-source collection.
### Observation contract and immutability

Before promotion, every Winterthur detail is transformed into a separate `contract_payload` and validated with JSON Schema Draft 2020-12 against the frozen `posting_observation_v1_2.schema.json`. The original source JSON-LD remains in `structured_payload`. A contract failure retains RAW evidence, fails the collection run, and creates no `PostingObservation`.

`PostingObservation` is append-only through the model and read-only in Django Admin. Repeated runs create distinct historical observations. Governance is fail-closed: only `APPROVED`, or `AUTOMATION_REVIEW_REQUIRED` with explicit manual acknowledgement, can run; incompatible source metadata and all other legal states are blocked before network access.

## GATE-004: full Winterthur snapshot and green relevance

`TARGETED` runs require `--posting-id` and are never complete snapshots. `FULL_SOURCE` runs require `--full-snapshot` and become complete only when listing, detail, observation, assessment counts and posting-ID sets are identical. Green relevance is an append-only derivation using frozen taxonomy v0.4, NFKC, casefolding and literal matching; no AI, fuzzy matching or scores are used.


## GATE-005: Winterthur temporal lifecycle and source health

A `Posting` is the mutable lifecycle projection for one source-native identity. Immutable `PostingObservation` and `PostingLifecycleEvent` rows remain the audit history. A healthy full-source absence creates `NOT_FOUND`; closure requires two healthy negative scans separated by at least 48 hours. Outages and degraded runs never advance closure.

Run counters distinguish `listing_total_discovered` from `postings_in_scope`. Only `FULL_SOURCE` runs can generate negative lifecycle evidence. No scheduler is included.

## GATE-010 point-in-time dashboard

Build the pinned MapLibre assets and install the headless browser once:

    npm ci
    npm run build-assets
    python -m playwright install chromium

Create a dashboard snapshot from aligned successful upstream runs. This command is
network-free and does not collect, geocode, deduplicate, or reclassify:

    python manage.py build_dashboard_snapshot \
      --as-of 2026-08-10T12:00:00+02:00 \
      --dedup-run <UUID> \
      --premium-run <UUID>

Run Django and open http://127.0.0.1:8000/jobs/. Public endpoints are:

    GET /api/v1/dashboard/snapshots/current/
    GET /api/v1/dashboard/snapshots/<snapshot_uuid>/
    GET /api/v1/dashboard/snapshots/<snapshot_uuid>/vacancies/
    GET /api/v1/dashboard/snapshots/<snapshot_uuid>/vacancies.geojson
    GET /api/v1/dashboard/snapshots/<snapshot_uuid>/vacancies/<run_vacancy_key>/
    GET /postings/<posting_uuid>/?snapshot=<snapshot_uuid>

DASHBOARD_MAP_STYLE_URL may contain an explicitly licensed MapLibre style URL.
When empty, the page uses a local blank style and the complete public table remains usable.
Set DASHBOARD_MAP_ATTRIBUTION to the attribution required by the configured provider.
Automated tests never contact a tile provider.

Run the browser acceptance independently with:

    make browser-test

The dashboard is an observed-source snapshot, not Day-0 or a complete Swiss labour-market census.
Headline market counters remain unavailable until a later gate authorizes adequate coverage.
