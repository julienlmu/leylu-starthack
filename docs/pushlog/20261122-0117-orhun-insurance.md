**Task:** R91/R92 too_low (insurance) · **Agent:** Claude Code

# The customer's cargo insurance premium goes into the all-in price (INSURANCE)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/requote (quick patch; PR #231 is the full version)
- `shapes.insurance_premium`: parses goods value × cover % × premium rate ("worth 81000 EUR, cover is 110 %, premium rate 0.30 %" gives EUR 267.30; R91 gives 96.80). The result is stored as rfq.insurance_eur.
- `agent/backend.py Backend.price` adds it to every EUR option and to chosen (total, total_eur, breakdown line). `backend/booking.py _new_total` adds it to the fresh-rate total, so the booking's price check doesn't see a change.
- The mail says "cargo insurance included" (en/de). The premium is kept across re-quotes.
- Tests: test_night_traps.py; agent 2390 passed, backend 242.
