# GigBid tasks.  make help
# On Windows without `make`, run the commands under each target directly (from the project root).
PYTHON ?= python
COMPOSE = docker compose -f infra/docker-compose.yml
export BUILDX_BAKE_ENTITLEMENTS_FS = 0

.PHONY: help dev test lint eval smoke-eval seed demo down graphs snapshots web e2e

help:            ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

dev:             ## run GigSim (:8001) + API with the web UI (:8000) locally (SQLite persistence)
	$(PYTHON) -m uvicorn gigsim.app:app --port 8001 & \
	$(PYTHON) -m apps.api.main

test:            ## unit + integration + MCP + contract tests
	$(PYTHON) -m pytest -q

lint:            ## Python lint (ruff) + TypeScript type check
	$(PYTHON) -m ruff check .
	cd apps/web && npx tsc -b

eval:            ## full evaluation: retrieval, ablation, decisions + GigSim reply rate -> evals/results/*.json
	$(PYTHON) -m evals.runners.rag_eval
	$(PYTHON) -m evals.runners.ablation
	LLM_PROFILE=fake RAG_VARIANT=bm25 $(PYTHON) -m evals.runners.graph_eval --name graph_rules_bm25
	LLM_PROFILE=fake RAG_VARIANT=bm25 $(PYTHON) -m evals.runners.graph_eval --per-persona 10 --name smoke
	$(PYTHON) -m evals.runners.check_thresholds smoke

smoke-eval:      ## 30-job smoke eval (what CI runs on every pull request) + threshold check
	LLM_PROFILE=fake RAG_VARIANT=bm25 $(PYTHON) -m evals.runners.graph_eval --per-persona 10 --name smoke
	$(PYTHON) -m evals.runners.check_thresholds smoke

seed:            ## regenerate synthetic personas and the labelled dev set
	$(PYTHON) scripts/generate_personas.py
	$(PYTHON) scripts/make_dev_set.py

demo:            ## everything in Docker: Postgres, GigSim, API + web UI at http://localhost:8000
	$(COMPOSE) up --build -d
	@echo "open http://localhost:8000"

down:            ## stop the Docker stack (data volumes are kept)
	$(COMPOSE) down

graphs:          ## render both LangGraph graphs to docs/images/*.mmd
	$(PYTHON) scripts/run_bid.py --graph

snapshots:       ## regenerate MCP tool-schema snapshots after an INTENDED tool change
	UPDATE_SNAPSHOTS=1 $(PYTHON) -m pytest tests/contract -q

web:             ## build the React app (served by the API)
	cd apps/web && npm ci && npm run build

e2e:             ## Playwright tests (needs `make dev` running with LLM_PROFILE=fake)
	cd apps/web && npx playwright test
