# Extraction: volumes given per lot are kept and summed (RFQ #7 was handed to a person)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/lot-volumes
- What changed: each piece line in the extraction schema has its own volume_m3 (cbm for the whole line); to_rfq sums them when the mail gives no single total. RFQ #7 (16:37, "Lot 1: 618 kg / 0.74 cbm, Lot 2: 380 kg / 1.65 cbm") lost both volumes and was handed over as "missing: dimensions or volume"; Orhun answered it by hand (accepted)
- Files touched: agent/extract.py, agent/test_rfq_agent.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: cd agent && uv run pytest -q → 73 passed; the real #7 mail through gpt-6-luna with the new schema: both lot volumes read, volume 2.39, nothing missing, $0.00013
- Known issues / TODO: none
- Heads-up for teammates: Julien, small schema change in extract.py (one more nullable field per piece)
