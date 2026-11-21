# DG: negated goods words are no alarm ("non-flammable", "no lithium batteries")
- Who: Orhun (tool: Claude Code)
- Branch: orhun/dg-negations
- What changed: agent/dg.py NEGATED also covers flammable and lithium (batteries / ion / cells) after non/not/no/without/free of/kein/ohne, and "lithium-free". Before, "Goods: non-flammable cosmetics, not dangerous" and "Spare parts, no lithium batteries included" were flagged as dangerous goods, so a general-cargo quote asked for the DGD + MSDS and the bid request said DG
- Files touched: agent/dg.py, agent/test_dg.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: cd agent && uv run pytest -q → 131 passed on main e017012 (new test fails on the old regex); real DG ("laptops with lithium-ion batteries", perfume) still detected
- Known issues / TODO: none
- Heads-up for teammates: Julien, small regex change in your folder
