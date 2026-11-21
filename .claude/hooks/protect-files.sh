#!/usr/bin/env bash
# Protects shared files. The Lead can edit them with: ALLOW_SHARED=1 claude
[ "$ALLOW_SHARED" = "1" ] && exit 0
INPUT=$(cat)
if echo "$INPUT" | grep -Eq '"file_path": *"[^"]*(docs/CONTRACT\.md|package-lock\.json|pnpm-lock\.yaml|uv\.lock|\.env|\.github/)'; then
  echo "Blocked: shared file (CONTRACT/lockfile/.env/.github). Propose the change to your human; the Lead applies it." >&2; exit 2
fi
exit 0
