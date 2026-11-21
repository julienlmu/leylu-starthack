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
# Mixed lots and the trucker rule (round 9)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/weight-precision (PR #52)
- What changed:
  - agent/extract.py: a shipment mixing lots with a volume and lots with dimensions ("Lot 1: 730 kg / 1.68 cbm, Lot 2: 4 cartons each 110x110x52, Lot 3: 5 cases each 120x100x8") sums them per line (4.68 cbm) instead of handing the RFQ to a person (#48 regression)
  - backend/pricing.py: PICKUP_CHOICE default back to balanced (ratio 50/50). It matches 5U in all door-to-port rounds: 2, 4 (full 60) and 9 (cheapest trucker was 3.2 % below the best: 45.59 instead of 60)
- How verified: agent 88, backend 61 passed (new: mixed lots 4.68 cbm; round 9 trucker = Domblick)
