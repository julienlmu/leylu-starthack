# A1 (model): gpt-6-luna with reasoning off is the live extraction model (Orhun's decision), measured live
- Who: Orhun (tool: Claude Code)
- Branch: orhun/llm-gpt-6-luna (from main; touches Julien's agent/llm.py, so Julien please review)
- What changed:
  - agent/llm.py: default model gpt-6-luna (an empty LLM_MODEL= now also falls back to it); price (0.10, 0.50) USD per 1M tokens; requests for gpt-6-luna send reasoning_effort "none"
  - test: the gpt-6-luna request carries reasoning_effort none and is priced right
- Measured live through the 5U gateway, same prompt and schema, 2 RFQs (German MUC-JFK fixture, English FRA-LAX "150 kg each"):
  | model | in / out tokens | cost per call | time | extraction |
  |---|---|---|---|---|
  | gpt-4o-mini | 435 / 113, 405 / 97 | $0.000133, $0.000119 | 3.5 s, 2.0 s | FRA-LAX wrong: 75 kg per piece instead of 150 |
  | gpt-6-luna, default reasoning | 433 / 293 (165 reasoning), 403 / 236 | $0.000190, $0.000158 | 3.7 s, 3.1 s | both right |
  | gpt-6-luna, reasoning_effort none | 433 / 120, 403 / 104 | $0.000103, $0.000092 | 2.0 s, 1.5 s | both right |
  - Prices are OpenAI list prices from public price trackers (gpt-6-luna $0.10 in / $0.50 out); the gateway's own cost counter is what 5U scores, check it on /v1/board/me after the first hour
  - reasoning_effort "minimal" is refused by gpt-6-luna (400); allowed: none, low, medium, high, xhigh
- Files touched: agent/llm.py, agent/test_agent_core.py
- Contract/API changes: none
- New env vars / packages: LLM_MODEL=gpt-6-luna (set it in your own .env, or leave it empty)
- How verified: `cd agent && uv run pytest -q` → 39 passed; live extraction through llm.chat_json with gpt-6-luna on both RFQs: right fields, $0.000103 and $0.000092
- Known issues / TODO: .env.example still says gpt-4o-mini (it changes in PR #14, update after the merges)
- Heads-up for teammates: anyone running the agent with LLM_MODEL=gpt-6-luna needs this change, else every RFQ fails with "No price for gpt-6-luna"
