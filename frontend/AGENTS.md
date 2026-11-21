# frontend/AGENTS.md
<!-- Folder-specific rules. Root AGENTS.md and AI_GUIDELINES.md always apply. Keep short. -->
Owner: Batu. Don't edit files outside this folder without asking.

## Commands (run from `frontend/`)
- Install: `pnpm install`
- Run: `pnpm dev` → http://localhost:3000 (`/api/*` is proxied to `BACKEND_URL`, default `http://localhost:8000`)
- Check: `pnpm lint && pnpm exec tsc --noEmit && pnpm build`

## Rules
- Data shapes live in `lib/types.ts` and must match docs/CONTRACT.md exactly.
- All backend calls go through `lib/api.ts`. If the backend is down it falls back to `lib/mock.ts` and the header shows "mock data" (the 500s in the browser console are that fallback).
- shadcn components in `components/ui/` are generated (`pnpm dlx shadcn add <name>`); don't hand-edit them.
- pnpm 12 blocks dependency build scripts: allowed ones are listed under `allowBuilds` in `pnpm-workspace.yaml`.
