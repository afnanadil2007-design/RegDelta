# RegDelta developer entrypoints. A fresh clone reaches a working demo via:
#   make setup && make ingest && make seed && make dev
.DEFAULT_GOAL := help
.PHONY: help setup up down migrate install corpus ingest graph embed obligations seed \
	dev dev-api dev-web eval eval-retrieval eval-suites eval-gate labels gold mcp \
	e2e test lint typecheck fmt

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: up migrate install ## Bring up postgres, run migrations, install deps

up: ## Start postgres (and build images) via docker-compose
	docker compose up -d postgres

down: ## Stop the stack
	docker compose down

migrate: ## Apply database migrations
	cd backend && alembic upgrade head

install: ## Install backend + frontend dependencies
	cd backend && python -m pip install -e ".[dev]"
	cd frontend && npm install

corpus: ## Generate the synthetic circular corpus
	python -m ingestion.generate_corpus

ingest: ## Ingest circulars from data/circulars into the database
	python -m ingestion.run --no-vision

graph: ## Build the citation and supersession graph
	python -m ingestion.build_graph

embed: ## Embed chunks and policy clauses
	python -m ingestion.embed

seed: ## Build a fully working demo database end to end
	python -m ingestion.seed

obligations: ## Extract obligations (rules mode needs no API key)
	python -m ingestion.extract_obligations --mode rules

dev: ## Run api + web together
	docker compose up api web

dev-api: ## Run the API with autoreload
	cd backend && python run_api.py --reload

dev-web: ## Run the Vite dev server
	cd frontend && npm run dev

eval: ## Four-mode retrieval evaluation on the fixed sample (slow: reranking is ~40 s/query on CPU), then the suites
	python -m evaluation.run_eval --persist
	python -m evaluation.report
	python -m evaluation.run_suites

eval-retrieval: ## Four-mode retrieval evaluation on the fixed sample
	python -m evaluation.run_eval --persist

eval-fast: ## Dense, lexical and hybrid over every gold query (minutes, no reranking)
	python -m evaluation.run_eval --full-fast --label full-fast

eval-suites: ## Extraction, refusal, groundedness, latency/cost
	python -m evaluation.run_suites

eval-gate: ## CI gate: hybrid Recall@10/MRR on the CI corpus against evaluation/baseline.json
	python -m evaluation.check_baseline

labels: ## Rebuild the obligation label set
	python -m evaluation.build_extraction_labels --count 30

gold: ## Rebuild the retrieval gold set and its 60-citation sample manifest
	python -m evaluation.build_gold_set --sample 60

mcp: ## Demonstrate the MCP server over STDIO
	python -m mcp_server.test_mcp_client

test: ## Run backend + frontend tests
	cd backend && pytest -q
	cd frontend && npm run test -- --run

e2e: ## Playwright smoke flows (needs `make seed` and `make dev` running first)
	cd frontend && npx playwright install --with-deps chromium && npm run e2e

lint: ## Ruff lint (backend + top-level packages)
	cd backend && ruff check .
	ruff check ingestion evaluation mcp_server

typecheck: ## mypy on app/ai (must be clean)
	cd backend && mypy app/ai

fmt: ## Format Python
	cd backend && ruff format .
	ruff format ingestion evaluation mcp_server
