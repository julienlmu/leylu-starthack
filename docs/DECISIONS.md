# DECISIONS.md — decision log (append only)
Format: `- [time] [who] decision — why`

- [Sat 13:10] [Lead] Stack: <...> — everyone knows it, fast setup
- [Sat 14:50] [Julien] Case: 5U AI "Build the Forwarder" (allocated by organisers) — full plan in docs/PLAN.md
- [Sat 14:50] [Julien] Stack: Python 3.12 + uv (agent, backend: FastAPI + SQLite), Next.js + shadcn (frontend), `openai` SDK via 5U gateway — gateway is OpenAI-only; fewest moving parts
- [Sat 14:50] [Julien] Exactly one tiny gateway call per RFQ; routing, pricing and replies are code + templates — LLM cost is 40% of the score and a quote without a gateway call gets no cost points
- [Sat 14:50] [Julien] Owners: Julien agent/, Orhun backend/ + Lead, Batu frontend/, Ulas 5U contact/data/pitch — token-heavy coding to Julien and Orhun
