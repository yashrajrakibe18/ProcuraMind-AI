.PHONY: inspect install install-dev run-api run-web test lint format eval samples seed migrate up down
PY ?= python

install-dev:        ## install everything needed to develop and test
	$(PY) -m pip install -r requirements-dev.txt && $(PY) -m pip install --no-deps -e .

run-api:            ## start the API on :8000 (reads .env)
	PYTHONPATH=src:apps/api $(PY) -m uvicorn app.main:app --reload --port 8000

run-web:            ## start the Streamlit UI on :8501
	cd apps/web && API_BASE_URL=http://localhost:8000/api/v1 streamlit run app.py

test:               ## run the whole test-suite
	$(PY) -m pytest

lint:               ## static checks
	ruff check . && ruff format --check .

format:
	ruff format . && ruff check . --fix

eval:               ## reproducible retrieval evaluation on the synthetic set
	PYTHONPATH=src $(PY) scripts/evaluate_retrieval.py --k 3

samples:            ## regenerate synthetic sample documents into data/samples
	PYTHONPATH=src $(PY) scripts/generate_sample_data.py

seed:               ## upload samples to a running API and run an analysis
	PYTHONPATH=src $(PY) scripts/seed_demo_data.py

migrate:            ## apply database migrations
	alembic upgrade head

up:                 ## docker compose stack
	docker compose up --build -d

down:
	docker compose down

inspect:            ## show environment capabilities
	PYTHONPATH=src $(PY) scripts/inspect_environment.py
