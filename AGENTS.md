# AGENTS.md
<!-- Keep short (<150 lines). Only what an agent can't infer from code. Lead owns this file.
     When an agent makes the same mistake twice, add one line under "Known gotchas". -->

**IMPORTANT: Before your first task, read `AI_GUIDELINES.md`. Every push MUST include a push log entry in `docs/pushlog/` (see AI_GUIDELINES.md §3).**

## What we're building
<Fill in after 12:55: one sentence problem, one sentence solution.>
Demo flow (everything serves this): <user does X → sees Y → result Z>
Deadline: Sunday 12:45.

## Commands (run from repo root)
- Setup: `make setup`   (also enables git hooks)
- Run: `make dev`       (uses PORT env, default 3000)
- **Verify: `make check`** — lint + typecheck + tests. Run before saying "done".
- Single test: `<npm test -- path | pytest path::test>`

## Stack
<e.g. Next.js 15 + TypeScript + Tailwind | FastAPI + Python 3.12 + uv>
Package manager: <pnpm | uv>. Don't use others (no `npm install`, no `pip install`).

## Folders and owners
- `frontend/` person 4 · `backend/` person 3 · `agent/` person 2 · `docs/` + root files person 1 (Lead)
- Each folder has its own `AGENTS.md`; read it when working there.
- Single source of truth between modules: `docs/CONTRACT.md`.

## Boundaries (full list in AI_GUIDELINES.md §5)
- 🚫 Never push to `main`, force push, or commit `.env`/keys.
- 🚫 No AI attribution in commits/PRs (no `Co-Authored-By: Claude`, no "Generated with"). Commits carry only the human's name.
- ⚠️ Ask before touching other folders, `docs/CONTRACT.md`, packages/lockfiles.
- ✅ Always run `make check` and write a push log entry before pushing.

## Known gotchas
- <e.g. Partner API is slow (5s+): use `MOCK_API=1` in dev.>

## Where things are
- `AI_GUIDELINES.md` — full workflow: start task, push log, finish task, boundaries
- `docs/pushlog/` — one file per push; read the last 10 at the start of each task
- `docs/TASKS.md` — who does what · `docs/DECISIONS.md` — decisions · `docs/CONTRACT.md` — API/data shapes
