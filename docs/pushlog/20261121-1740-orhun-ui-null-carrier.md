# UI: a hand-written quote (carrier null) no longer crashes the session list
- Who: Orhun (tool: Claude Code)
- Branch: orhun/ui-null-carrier
- What changed: frontend/lib/format.ts shortCarrier() returns "manual" for a quote without a carrier. Orhun's manual reply on round 15 is stored with carrier null (#67), and SessionStrip (session-rack.tsx:251) threw a TypeError for every render
- Files touched: frontend/lib/format.ts
- How verified: pnpm lint, tsc --noEmit clean
- Heads-up for teammates: Batu, one-line fix in your folder
