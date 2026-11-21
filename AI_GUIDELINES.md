# AI_GUIDELINES.md — Rules for every AI coding agent on this team

> Applies to Claude Code, Cursor, Codex, Copilot and any other agent.
> `AGENTS.md` (loaded automatically) points here. Read this file fully before your first task in a session.

## 0. The one goal
Ship ONE working end-to-end demo flow by **Sunday 12:45** (hard deadline).
Simple working code beats clean architecture. If a change does not serve the demo flow, don't make it.

## 1. Before you start a task
1. Sync: `git fetch origin && git switch -c <name>/<task-id>-<short-desc> origin/main`
2. Read, in this order:
   - `docs/TASKS.md` — find your task, set it to `DOING` + your branch name, commit only that file, push.
   - The **last 10 push log entries**: `ls docs/pushlog | tail -10` and read them. This is how you learn what teammates' agents changed recently.
   - `docs/CONTRACT.md` (API + data shapes) and `docs/DECISIONS.md`.
3. If the task conflicts with the contract, decisions, or a recent push log entry: **stop and ask your human.**
4. If the task can't be described in one sentence, write a 3–5 bullet plan and get approval before coding.

## 2. While you work
- Only edit files inside your task's folder (`frontend/`, `backend/`, `agent/`). Need anything else? Ask first.
- Small, single-purpose commits. Message format: `<area>: <what>` — e.g. `backend: add /api/routes endpoint`.
- Run `make check` after every meaningful step.
- Mock slow or external services (LLM, partner APIs) behind one module so the demo never depends on the network.
- A branch should not live longer than ~45–60 min. Ship the working part, open a new task for the rest.

## 2b. Authorship — commits and PRs show ONLY the human's name
- Commit with the human's own git identity (`git config user.name` / `user.email`). Never change git config.
- Never add `Co-Authored-By: Claude/Cursor/Codex/...`, "Generated with ...", "🤖", session links or any AI attribution to commits, PR titles/bodies or code comments.
- Don't mention the AI tool in commit messages. (The push log "Who" line may name the tool; that file is internal.)
- Enforced by `.githooks/commit-msg` (strips such lines) and, for Claude Code, `"attribution": {"commit": "", "pr": ""}` in `.claude/settings.json`.

## 3. Before every push — write a push log entry (REQUIRED)
Every push of code must include a new file in `docs/pushlog/`. One file per push, so entries never cause merge conflicts.

**File name:** `docs/pushlog/<YYYYMMDD-HHMM>-<name>-<task-id>.md` (e.g. `20261121-1530-orhun-B1.md`)

**Content (copy this template, keep it short):**
```markdown
# <task-id>: <one-line summary>
- Who: <human name> (tool: <Claude Code | Cursor | Codex | ...>)
- Branch: <branch-name>
- What changed: <2–4 bullets, user-visible behaviour first>
- Files touched: <main files/folders>
- Contract/API changes: <none | describe — must match docs/CONTRACT.md>
- New env vars / packages: <none | list>
- How verified: <make check result + manual test done>
- Known issues / TODO: <none | list>
- Heads-up for teammates: <anything other agents must know, or "none">
```
The pre-push git hook blocks a push without a new push log file (set `SKIP_PUSHLOG=1` only for a push that changes nothing but `docs/TASKS.md`).

## 4. Finishing a task
1. `git fetch origin && git rebase origin/main` — resolve conflicts only in your own files; otherwise stop and ask.
2. `make check` must pass. Never say "done" without showing its output.
3. Write the push log entry (section 3), commit it.
4. `git push -u origin HEAD`, then `gh pr create --fill` and fill in the PR template (paste the push log content into the PR description).
5. Set your task in `docs/TASKS.md` to `REVIEW`. If you made a notable choice, append one line to `docs/DECISIONS.md`.

## 5. Boundaries
✅ **Always**
- Follow sections 1–4. Keep diffs small. Show evidence (`make check` output), not claims.

⚠️ **Ask your human first**
- Touching another person's folder or root files.
- Changing `docs/CONTRACT.md`, adding a package, touching lockfiles or `.github/`.
- Deleting files, large refactors, new folder structure.

🚫 **Never**
- Add AI attribution (Co-Authored-By, "Generated with") to commits or PRs.
- Push to `main`, force push, `git reset --hard`, rewrite history.
- Commit, print or hard-code `.env` contents or API keys.
- Delete/skip tests or weaken checks to make `make check` pass.
- Add features, abstractions or "might need later" code nobody asked for.

## 6. When you get stuck
- Two failed fix attempts in a row → stop, summarise what you learned, ask your human.
- If a teammate's code seems broken, don't fix it in your branch: tell your human, who tells the owner.
- If you discover a gotcha other agents will hit, add it to your push log "Heads-up" AND ask your human to add one line to `AGENTS.md` → "Known gotchas".
