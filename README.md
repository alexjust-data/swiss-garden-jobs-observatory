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
