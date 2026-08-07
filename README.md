# Swiss Garden Jobs Observatory

This repository contains the Gate-001 repository baseline for a modular Django monolith.

## Requirements

- Python 3.12
- Docker (for PostgreSQL local bootstrap)
- Git

## Quick start (clean checkout)

```bash
cp .env.example .env
docker compose up -d --wait db

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

python manage.py migrate --noinput
python manage.py runserver 0.0.0.0:8000
```

In PowerShell, use `Copy-Item .env.example .env` instead of `cp`. The example configuration
connects Django running on the host to PostgreSQL exposed by Docker at `127.0.0.1:5432`.
The credentials in `.env.example` are local-only example values and must not be reused in a
shared or production environment. Django loads `.env` explicitly and fails at startup when a
required database setting is absent; it does not fall back to SQLite.

To prove migrations work from a completely empty PostgreSQL database:

```bash
docker compose down -v
docker compose up -d --wait db
python manage.py migrate --noinput
```

## Validation

```bash
make setup
make migrate
make test
make lint
make typecheck
```

Tests and migrations use PostgreSQL. You can verify the active backend with:

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

## Scope implemented

- Django project bootstrap.
- PostgreSQL configuration loaded explicitly from `.env`, without a SQLite fallback.
- Local raw object store path (`data/raw`).
- SHA-256 helpers for byte buffers and files.
- `/health/` and `/api/health/` endpoints.
- `core.RawArtifact` model and initial migration.
- tests for health, RAW storage path safety, and SHA-256.
- lint + type checking + tests + GitHub Actions pipeline.
