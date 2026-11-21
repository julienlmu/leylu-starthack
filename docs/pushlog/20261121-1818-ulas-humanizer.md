# HUMANIZER: verdict on blader/humanizer for our mails
- Who: Ulas (tool: Claude Code)
- Branch: ulas/emergency-fixes
- What changed: docs/HUMANIZER.md: use the skill once offline on agent/templates.py (English first, then the other languages by hand), not at runtime (LLM cost, latency, numbers)
- Files touched: docs/HUMANIZER.md, docs/pushlog/
- Contract/API changes: none
- New env vars / packages: none
- How verified: read the repo README (26 patterns, MIT, skill install); docs only
- Known issues / TODO: none
- Heads-up for teammates: Orhun, a 15-minute job when accuracy/speed fixes are done
