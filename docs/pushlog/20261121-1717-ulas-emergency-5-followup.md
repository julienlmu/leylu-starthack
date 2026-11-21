# EMERGENCY-5-FOLLOWUP: update round 11 PDF DG diagnosis
- Who: Ulas (tool: Codex)
- Branch: ulas/emergency-fixes
- What changed: updated the top incident with current public-board counts, the PDF parsing cause on origin/main, fix branch `ulas/dg-pdf-round11`, and the required between-round restart.
- Files touched: docs/EMERGENCY_FIXES.md, docs/pushlog/
- Contract/API changes: none
- New env vars / packages: none
- How verified: read-only public board and watcher topic; focused PDF attachment test passed on the fix branch (6 passed). `/v1/board/me` and mailbox require the unavailable team key.
- Known issues / TODO: fix branch is pushed but not merged or deployed.
- Heads-up for teammates: merge/deploy `ulas/dg-pdf-round11` before the next PDF packing-list RFQ; restart only between rounds.
