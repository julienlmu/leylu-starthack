# Carrier bids in attachments are read (R65/R66)
- Who: Orhun
- Branch: orhun/bid-attachments
- What changed: agent/rfq_agent.py _carrier_round reads a bid's attachments (txt/pdf/docx/xlsx via /api/attachments/text, up to 3) in front of the mail body before parsing; since ~21:17 truckers and some airlines send "Please find our quotation attached (quotation-TRK-5937.txt / price-offer-TRK-5939.pdf)" and every one read as "no usable offer". BID_ATTACHMENTS=off switches it off.
- How verified: agent 1311 passed (an R66-style reply with a .txt quotation parses to EUR 245.10, TRK-5937)
