#!/usr/bin/env bash
# Blocks dangerous commands for Claude Code. exit 2 = block; stderr is shown to Claude.
INPUT=$(cat)
if echo "$INPUT" | grep -Eq 'git push[^"]*(--force|-f( |")|origin main|origin HEAD:main)'; then
  echo "Blocked: pushing to main or force pushing is not allowed. Push your branch and open a PR (AI_GUIDELINES.md §4)." >&2; exit 2
fi
if echo "$INPUT" | grep -Eq 'git (reset --hard|clean -fd|checkout -- \.)|rm -rf '; then
  echo "Blocked: irreversible command. Ask your human." >&2; exit 2
fi
if echo "$INPUT" | grep -Eq '(npm|yarn) install|pip install'; then
  echo "Blocked: ask your human before adding packages (the Lead manages lockfiles)." >&2; exit 2
fi
exit 0
