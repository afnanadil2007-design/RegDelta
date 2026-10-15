# RegDelta developer entrypoints (Linux). From a fresh clone:
#   cp .env.example .env
#   make setup     # postgres container, Python venv from the lockfile, npm ci
#   make db seed   # create + migrate the database, build the synthetic demo data
#   make dev-api   # terminal 1: API on 127.0.0.1:8000 (deterministic judge by default)
#   make dev-web   # terminal 2: web on 127.0.0.1:5173
.DEFAULT_GOAL := help
.PHONY: help setup up down venv install db migrate seed corpus ingest graph embed obligations \
	dev-api dev-web test test-backend test-frontend lint typecheck fmt check \
	eval eval-retrieval eval-fast eval-suites eval-gate gold labels real-corpus \
	e2e-db e2e mcp

# The project virtualenv when it exists, otherwise whatever python is on PATH (CI).
PY := $(shell [ -x backend/.venv/bin/python ] && echo $(CURDIR)/backend/.venv/bin/python || echo python)
TORCH_INDEX := https://download.pytorch.org/whl/cpu

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: up venv install ## Postgres container + Python venv + frontend packages

up: ## Start the pgvector Postgres container (loopback only)
	docker compose up -d postgres

down: ## Stop the containers (the data volume is kept)
	docker compose down

venv: ## Create backend/.venv (Python 3.11) if missing
	[ -x backend/.venv/bin/python ] || python3.11 -m venv backend/.venv

install: ## Install the locked backend dependencies and the frontend packages
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r backend/requirements.lock --extra-index-url $(TORCH_INDEX)
	$(PY) -m pip install -e backend --no-deps
	cd frontend && npm ci

db: ## Create the configured database if missing and migrate it to head
	$(PY) -m ingestion.prepare_db

migrate: ## Apply migrations to the configured database
	cd backend && $(PY) -m alembic upgrade head

seed: ## Synthetic corpus, citation graph, policy manual, embeddings, obligations, gold set
	$(PY) -m ingestion.seed

corpus: ## Regenerate the synthetic PDFs (deterministic)
	$(PY) -m ingestion.generate_corpus

ingest: ## Ingest the synthetic PDFs
	$(PY) -m ingestion.run --no-vision

graph: ## Rebuild the citation and supersession graph
	$(PY) -m ingestion.build_graph

embed: ## Embed chunks and policy clauses
	$(PY) -m ingestion.embed

obligations: ## Extract obligations with the rule extractor (no API key)
	$(PY) -m ingestion.extract_obligations --mode rules

dev-api: ## Run the API with autoreload
	cd backend && $(PY) run_api.py --reload

dev-web: ## Run the Vite dev server
	cd frontend && npm run dev

test: test-backend test-frontend ## Backend and frontend tests

test-backend: ## Backend tests against the regdelta_test database (created if missing)
	POSTGRES_DB=regdelta_test $(PY) -m ingestion.prepare_db
	cd backend && POSTGRES_DB=regdelta_test PYTHONPATH=.:.. $(PY) -m pytest -q

test-frontend: ## Lint, format check, typecheck, unit tests and production build
	cd frontend && npm run lint && npm run format:check && npm run typecheck && npx vitest run && npm run build

lint: ## Ruff lint and format check over all Python
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

typecheck: ## mypy (app/ai must be clean)
	cd backend && $(PY) -m mypy app/ai

fmt: ## Format Python
	$(PY) -m ruff format .

check: lint typecheck test ## The fast gates CI runs

eval: ## Four-mode retrieval evaluation on the fixed sample (slow: reranking is ~40 s/query on CPU)
	$(PY) -m evaluation.run_eval --persist
	$(PY) -m evaluation.report
	$(PY) -m evaluation.run_suites

eval-retrieval: ## Four-mode retrieval evaluation on the fixed sample only
	$(PY) -m evaluation.run_eval --persist

eval-fast: ## Dense, lexical and hybrid over every gold query (minutes, no reranking)
	$(PY) -m evaluation.run_eval --full-fast --label full-fast

eval-suites: ## Extraction, refusal, groundedness, latency/cost suites
	$(PY) -m evaluation.run_suites

eval-gate: ## CI gate: hybrid Recall@10/MRR on the CI corpus against evaluation/baseline.json
	$(PY) -m evaluation.check_baseline

gold: ## Rebuild the retrieval gold set and its 60-citation sample manifest
	$(PY) -m evaluation.build_gold_set --sample 60

labels: ## Rebuild the obligation label set
	$(PY) -m evaluation.build_extraction_labels --count 30

real-corpus: ## Re-fetch the official SEBI documents named by the manifest and verify checksums
	$(PY) -m ingestion.scrape_sebi --fetch-missing

e2e-db: ## Disposable regdelta_e2e database with the seeded synthetic demo data
	POSTGRES_DB=regdelta_e2e $(PY) -m ingestion.prepare_db
	POSTGRES_DB=regdelta_e2e $(PY) -m ingestion.seed --skip-corpus

e2e: ## Playwright end-to-end tests (starts the API and a production build itself)
	cd frontend && REGDELTA_PYTHON=$(PY) npx playwright test

mcp: ## Demonstrate the MCP server over STDIO
	$(PY) -m mcp_server.test_mcp_client
