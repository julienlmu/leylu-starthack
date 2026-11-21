# Trucker bid hardening (R68 rejected too_low)
- Who: Orhun
- Branch: orhun/deploy-next5
- What changed: agent/bids.py drops out-of-offer extras ("Not part of this offer: waiting time …, 45.00 EUR for each hour") before parsing and reads a bare "Total 130.70" when the currency is only in the PDF table header; backend/pricing.py drops trucker bids under EUR 60, under 0.05 EUR/kg or 3x below the median, and gives bids without transit the median transit.
- How verified: agent 1314, backend 93 (R68's real PDF text parses to EUR 130.70; the R68 trucker set drops the 45.00 bid)
