# All agents and CI use these commands. Fill in once the stack is chosen.
.PHONY: setup dev check
setup:
	git config core.hooksPath .githooks
	@echo "TODO: e.g. pnpm install && (cd backend && uv sync)"
dev:
	@echo "TODO: e.g. pnpm --dir frontend dev & uv run --directory backend uvicorn app:app --port $${PORT:-8000}"
check:
	@echo "TODO: lint + typecheck + test, e.g. pnpm -r lint && pnpm -r test && (cd backend && uv run pytest -q)"
