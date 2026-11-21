# leyl--starthack

## Team setup (agent guidelines)
1. (Done) The agent guidelines template is already in this repo.
2. GitHub → Settings → Branches → `main`: require PR, require `ci` check, block force pushes.
3. Everyone after cloning: `make setup` (enables git hooks: no push to main, push log required, no secrets, AI attribution stripped from commit messages).
   Also check `git config user.name` and `user.email` are YOUR name — that is what GitHub shows.
4. Once the stack is chosen: fill in the 3 Makefile commands, AGENTS.md (What/Stack/Commands) and folder AGENTS.md files.
5. Sanity check in every tool: ask "According to AGENTS.md and AI_GUIDELINES.md, what must you do before pushing?"

Which tool reads what:
- Claude Code: CLAUDE.md (→ @AGENTS.md + @AI_GUIDELINES.md), .claude/settings.json (permissions + hooks), .claude/skills/
- Codex / Cursor / Copilot: AGENTS.md (root + nested), which tells them to read AI_GUIDELINES.md
- Everyone: .githooks/ (tool-independent), CI, branch protection
