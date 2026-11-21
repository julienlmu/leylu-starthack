# AGENTS.md
<!-- Keep short (<150 lines). Only what an agent can't infer from code. Lead owns this file.
     When an agent makes the same mistake twice, add one line under "Known gotchas". -->

**IMPORTANT: Before your first task, read `AI_GUIDELINES.md`. Every push MUST include a push log entry in `docs/pushlog/` (see AI_GUIDELINES.md §3).**

## What we're building
5U AI challenge "Build the Forwarder": an air-freight RFQ arrives in our mailbox every 6 minutes, and only a fast, correctly priced, cheap-to-produce quote scores.
We build an AI air forwarder that quotes every RFQ in its thread within 2 minutes at the best all-in price, books by rate ID, answers tracking from its CRM, and shows everything in a live Sessions UI.
Demo flow (everything serves this): RFQ mail arrives → Sessions UI streams routing, extraction, prices and bids → quote sent within 2 min with its cost shown → customer accepts → booked → tracking question answered from the CRM.
Full plan: `docs/PLAN.md`. Deadline: Sunday 12:45 (confirm 5U's deadline).

## Commands (run from repo root)
- Setup: `make setup`   (also enables git hooks)
- Run: `make dev`       (uses PORT env, default 3000)
- **Verify: `make check`** — lint + typecheck + tests. Run before saying "done".
- Single test: `<npm test -- path | pytest path::test>`

## Stack
Python 3.12 + uv (`agent/`, `backend/`: FastAPI + SQLite) · `openai` SDK via 5U's LLM gateway (OpenAI only) · Next.js + TypeScript + Tailwind + shadcn/ui (`frontend/`).
Package manager: uv and pnpm. Don't use others (no `npm install`, no `pip install`).

## Folders and owners
- `agent/` Julien · `backend/` + `docs/` + root files Orhun (Lead) · `frontend/` Batu · `pitch/`, 5U contact, fixtures Ulas
- Tasks per person: `docs/TASKS.md`.
- Each folder has its own `AGENTS.md`; read it when working there.
- Single source of truth between modules: `docs/CONTRACT.md`.

## Boundaries (full list in AI_GUIDELINES.md §5)
- 🚫 Never push to `main`, force push, or commit `.env`/keys.
- 🚫 No AI attribution in commits/PRs (no `Co-Authored-By: Claude`, no "Generated with"). Commits carry only the human's name.
- ⚠️ Ask before touching other folders, `docs/CONTRACT.md`, packages/lockfiles.
- ✅ Always run `make check` and write a push log entry before pushing.

## Known gotchas
- LLM cost is 40% of the score: every LLM call goes through `agent/llm.py`. Budget: one tiny call per RFQ (zero calls also scores zero cost points).
- The first reply in a customer's thread is the quote. Never send acks or provisional mails.
- System Python may be 3.8: let uv provide 3.12, don't use the system `python3`.
- Keys live in the root `.env` (gitignored): `FIVEU_API_KEY` (kit card) and `GATEWAY_OPENAI_KEY`. After filling them in run `cd agent && uv run --env-file ../.env python setup_5u.py` once.

## Where things are
- `AI_GUIDELINES.md` — full workflow: start task, push log, finish task, boundaries
- `docs/pushlog/` — one file per push; read the last 10 at the start of each task
- `docs/TASKS.md` — who does what · `docs/DECISIONS.md` — decisions · `docs/CONTRACT.md` — API/data shapes
