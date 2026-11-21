# Bookings carry the full shipment weight (rounds 5 and 6 did not count as booked)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/weight-precision (on top of #48)
- What changed: to_rfq keeps the per-piece weight to 6 decimals and the backend rounds the shipment weight to 2, so "12 pieces, 1228 kg" is priced and booked at 1228.00 kg, not 102.33 × 12 = 1227.96. The board shows rounds 5 (STR-EZE, 1227.96) and 6 (DUS-KUL, 1548.96) as not booked: no tracking question came for them (-20 points)
- Files touched: agent/extract.py, backend/pricing.py, agent/test_rfq_agent.py, backend/test_pricing.py
- Contract/API changes: none (Rfq.weight_kg is still per piece, now with more decimals)
- New env vars / packages: none
- How verified: agent 87, backend 60 passed (new: 1228 kg over 12 pieces adds up to 1228.0 again; booked weight 1228.0)
- Known issues / TODO: none
- Heads-up for teammates: Julien, two rounding lines
