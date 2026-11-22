**Task:** all of main live · **Agent:** Claude Code

# main (#230–#233) into the live branch, one insurance path
- Who: Orhun (tool: Claude Code)
- Branch: orhun/requote
- Merges main e5eb985: #230 (gross/net, currency, mailbox retry), #231 (insurance), #232 (Batu's #229 review fixes) and #233 (separate prices are no combined total).
- Insurance: main's `insurance.py` (Backend.price → insurance.add) is the one path. My quick patch d3bd7d2 is removed (backend.with_insurance, booking insurance_eur, the shapes hook). main's VALUE regex now also reads "the goods are worth 81000 EUR" (R92), the same as #234.
- Multi-shipment: MULTI_QUOTE is kept on top of #233. With a separate-price wish, every lot is priced and quoted in one mail. Without it, #233's lot-1 path applies.
- Tests: agent 2476 passed, backend 243. `test_night_traps::test_r91_r92_insurance_premium_is_added_once` covers R91 and R92 wording, with add() called twice.
