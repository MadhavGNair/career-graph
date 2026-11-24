# CareerGraph. Run `make help` for every target. All targets work in demo mode without keys.
SHELL := /bin/bash
.DEFAULT_GOAL := help
UV ?= uv
CG := $(UV) run careergraph
THREAD ?=
JOBS ?=
REJECT ?=
DEFER ?=
CHECKPOINT ?=
JOB ?=
ACTION ?= approve-all
SUITE ?= all
MODE ?= fake
IMAGE ?= careergraph:dev

.PHONY: help init setup doctor demo ui profile jobs run resume pending shortlist approve review \
	render render-sample history fork tracker test test-fast lint format typecheck check eval \
	export-labels docs-graphs docker-build docker-up k8s-lint pii-guard clean

help: ## List all targets with a one-line description
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

init: ## Create .env from .env.example and profiles/me from the example, then validate config
	@test -f .env || (cp .env.example .env && echo "created .env (demo mode)")
	@test -d profiles/me || (cp -R profiles/example profiles/me && echo "created profiles/me from profiles/example")
	@$(CG) validate-config

setup: ## Install dependencies with uv (Python 3.12)
	$(UV) sync

doctor: ## Check keys, mode, LaTeX, DB, profile files, config and worst-case spend
	@$(CG) doctor

demo: ## Full end-to-end demo with the fake LLM (no keys, no Docker), then prints how to open the UI
	APP_MODE=demo $(CG) demo

ui: ## Start the Streamlit UI (binds UI_HOST, default 127.0.0.1)
	$(CG) ui

profile: ## Run nodes 1-2 only: ingest your documents/GitHub and extract evidence
	$(CG) profile

jobs: ## Run nodes 3-5: find, analyse and score jobs; prints the shortlist (no pause, nothing saved as pending)
	$(CG) jobs

run: ## Run the full graph until the first pause (the shortlist); cron uses the same command
	$(CG) run

resume: ## Resume a halted thread (e.g. after a budget stop or crash): THREAD=...
	$(CG) resume $(THREAD)

pending: ## List threads waiting for your input
	$(CG) pending

shortlist: ## Show the shortlist of a paused thread: THREAD=...
	$(CG) shortlist $(THREAD)

approve: ## Resume the shortlist pause: THREAD=... JOBS=id1,id2 [REJECT=id3:too_junior] [DEFER=id4]
	$(CG) approve $(THREAD) --jobs "$(JOBS)" --reject "$(REJECT)" --defer "$(DEFER)"

review: ## Resume the document-review pause: THREAD=... [ACTION=approve-all|reject-all]
	$(CG) review $(THREAD) --action $(ACTION)

render: ## Re-render a saved application's documents: JOB=<posting id>
	$(CG) render $(JOB)

render-sample: ## Render the templates with sample data into outputs/sample/ (tests your own template)
	$(CG) render-sample

history: ## Show checkpoint history of a thread: THREAD=...
	$(CG) history $(THREAD)

fork: ## Replay a thread from a checkpoint (time travel): THREAD=... CHECKPOINT=...
	$(CG) fork $(THREAD) $(CHECKPOINT)

tracker: ## List tracked applications and their status
	$(CG) tracker list

test: ## Run the full test suite (includes the headless demo smoke test)
	$(UV) run pytest

test-fast: ## Run tests except slow end-to-end ones
	$(UV) run pytest -m "not slow"

lint: ## Ruff lint and format check
	$(UV) run ruff check src tests ui
	$(UV) run ruff format --check src tests ui

format: ## Auto-format and fix lint issues
	$(UV) run ruff format src tests ui
	$(UV) run ruff check --fix src tests ui

typecheck: ## Pyright type check
	$(UV) run pyright

check: lint typecheck test ## Lint, typecheck and test

eval: ## Run eval suites against thresholds: SUITE=all|match|extraction|verifier|injection MODE=fake|live
	$(CG) eval run --suite $(SUITE) --mode $(MODE)

export-labels: ## Export your own triage decisions as an eval dataset
	$(CG) eval export-labels

docs-graphs: ## Regenerate Mermaid diagrams from the compiled graphs into the READMEs
	$(CG) docs-graphs

docker-build: ## Build the runtime image (no push)
	docker build -f deploy/docker/Dockerfile -t $(IMAGE) .

docker-up: ## Run the UI with docker compose (add --profile postgres / --profile cron as needed)
	docker compose up --build

k8s-lint: ## helm lint + helm template | kubeconform (skips tools that are missing)
	@bash deploy/helm/lint.sh

pii-guard: ## Fail if personal files or secrets are tracked by git
	$(UV) run python -m careergraph.devtools.pii_guard

clean: ## Remove caches and demo databases (keeps your live DB and outputs)
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage data/cache
	rm -f data/careergraph-demo.db* data/langgraph-demo.db*
