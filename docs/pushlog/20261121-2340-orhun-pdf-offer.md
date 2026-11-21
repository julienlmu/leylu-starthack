# The offer as a PDF (or CSV) when the RFQ asks for it (R76 no_pdf_offer)
- Who: Orhun
- Branch: orhun/pdf-offer
- What changed: agent/offer_doc.py builds a one-page PDF without packages (route, pieces/kg/cbm, ready, airline, transit, "All-in price: EUR x" exactly as in the body) or a CSV; rfq_agent sets rfq.offer_doc from "as a PDF", "PDF attachment", "als PDF", "en PDF", … and _reply_quote attaches it (inbox.reply attachments). OFFER_DOCS=off.
- How verified: agent 1767 passed; the backend's own PDF reader reads the file back with the amount
