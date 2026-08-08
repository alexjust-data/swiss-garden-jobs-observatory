setup:
	python -m pip install --upgrade pip
	python -m pip install -r requirements-dev.txt
	python -m pip install -r requirements.txt

migrate:
	python manage.py migrate

dev:
	python manage.py runserver 0.0.0.0:8000

lint:
	ruff check .

typecheck:
	mypy src manage.py

test:
	pytest -q

import-reference-data:
	python manage.py import_reference_data

collect-winterthur:
	python manage.py collect_winterthur --full-snapshot --acknowledge-automation-review