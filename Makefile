# All agents and CI use these commands. Run from the repo root.
# Python: uv (one project per folder). Frontend: pnpm. Keys come from the root .env (never committed).
.PHONY: setup dev backend frontend agent agent-mock check check-agent check-backend check-frontend

# backend/ gets its uv project in B1; until then its targets are skipped.
HAS_BACKEND := $(wildcard backend/pyproject.toml)
ENV_FILE := $(if $(wildcard .env),--env-file ../.env,)

setup:
	git config core.hooksPath .githooks
	cd agent && uv sync
	$(if $(HAS_BACKEND),cd backend && uv sync,@echo "backend: no pyproject.toml yet, skipped")
	pnpm --dir frontend install --frozen-lockfile

# Backend on :8000 and frontend on :3000. The agent runs on its own (make agent / make agent-mock).
dev:
	$(MAKE) -j2 backend frontend

backend:
	$(if $(HAS_BACKEND),cd backend && uv run $(ENV_FILE) uvicorn app:app --reload --timeout-graceful-shutdown 1 --port $${PORT:-8000},@echo "backend: not built yet (B1)")

frontend:
	pnpm --dir frontend dev

# Live: real 5U mailbox and gateway. Needs FIVEU_API_KEY in .env and the backend running.
agent:
	cd agent && uv run $(ENV_FILE) python main.py

# Local: mails from agent/fixtures/inbox/, nothing is sent (the extraction still calls the gateway with the .env key).
agent-mock:
	cd agent && MOCK=1 uv run $(ENV_FILE) python main.py

# Lint + typecheck + tests. Run before saying "done". No `next build` here: it shares .next/ with a running `pnpm dev`.
check: check-agent check-backend check-frontend

check-agent:
	cd agent && uv run pytest -q

check-backend:
	$(if $(HAS_BACKEND),cd backend && uv run pytest -q,@echo "backend: no tests yet")

check-frontend:
	pnpm --dir frontend lint
	pnpm --dir frontend exec tsc --noEmit
