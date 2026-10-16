# RegDelta developer entrypoints (Linux). From a fresh clone:
#   cp .env.example .env   # pick free ports; see "Configuration" in README.md
#   make setup     # checks the stack, starts its postgres, venv from the lockfile, npm ci
#   make db seed   # create + migrate the database, build the synthetic demo data
#   make dev-api   # terminal 1: API on 127.0.0.1:$API_PORT (deterministic judge by default)
#   make dev-web   # terminal 2: web on 127.0.0.1:5173, proxying /api to that API
# Or everything in containers: make up venv install db seed stack-up.
#
# Make does not read .env. Docker Compose and the Python and Vite settings do,
# each with the same order: the process environment, then .env, then defaults.
.DEFAULT_GOAL := help
.PHONY: help setup up down stack-check stack-up venv install db migrate seed \
	corpus ingest graph embed obligations dev-api dev-web test test-backend test-frontend \
	lint typecheck fmt check eval eval-retrieval eval-fast eval-suites eval-gate gold labels \
	real-corpus e2e-db e2e mcp

# The project virtualenv when it exists, otherwise whatever python is on PATH (CI).
# Expanded at each use (=, not :=), so `make setup` installs into the venv that
# its own `venv` step has just created.
PY = $(shell [ -x backend/.venv/bin/python ] && echo $(CURDIR)/backend/.venv/bin/python || echo python)
TORCH_INDEX := https://download.pytorch.org/whl/cpu

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: up venv install ## Postgres container + Python venv + frontend packages

# Every target that starts or stops containers runs the check first: it prints
# the project, containers, volumes and ports, and refuses when a port is taken
# or the project's containers or volumes belong to another stack.
stack-check: ## Show what the Compose stack will touch; refuse a conflict
	python3 scripts/stack_check.py

up: ## Start this checkout's pgvector Postgres container (loopback only)
	python3 scripts/stack_check.py postgres
	docker compose up -d postgres

down: ## Stop and remove this project's containers (volumes, and so data, are kept)
	python3 scripts/stack_check.py --ownership-only
	docker compose down

# Images are built one at a time: building both at once does not fit in 8 GB.
stack-up: ## Build the api and web images and start the whole stack (web on $WEB_PORT)
	python3 scripts/stack_check.py
	docker compose build api
	docker compose build web
	docker compose up -d

# To reuse this machine's Hugging Face cache instead of downloading the models
# into the stack, add the overlay: COMPOSE_FILE=docker-compose.yml:docker-compose.host-models.yml
# (in the environment or .env); stack-check and every docker compose call read it.

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

# The disposable end-to-end database (override to keep another beside it).
REGDELTA_E2E_DB ?= regdelta_e2e

# Reuses the synthetic PDFs when `make seed` has written them, otherwise
# generates them (deterministically, so a fresh clone gets the same corpus).
e2e-db: ## Disposable regdelta_e2e database with the seeded synthetic demo data
	POSTGRES_DB=$(REGDELTA_E2E_DB) $(PY) -m ingestion.prepare_db
	POSTGRES_DB=$(REGDELTA_E2E_DB) $(PY) -m ingestion.seed $(if $(wildcard data/synthetic/pdf/*.pdf),--skip-corpus)

e2e: ## Playwright end-to-end tests (starts the API and a production build itself)
	cd frontend && REGDELTA_PYTHON=$(PY) REGDELTA_E2E_DB=$(REGDELTA_E2E_DB) npx playwright test

mcp: ## Demonstrate the MCP server over STDIO
	$(PY) -m mcp_server.test_mcp_client
