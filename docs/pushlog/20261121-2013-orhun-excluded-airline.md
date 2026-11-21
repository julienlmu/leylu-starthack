# Airlines the customer rules out are never quoted (R42 excluded_airline)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/excluded-airline
- What changed: agent/exclusions.py finds "do not offer/use/book ... <airline name> (XX)" sentences, remembers them per customer address (excluded_airlines.json), rfq.excluded_airlines; those airlines are not asked for bids and backend/pricing.py drops their options before choosing. EXCLUSIONS=off switches it off.
- How verified: agent 366, backend 74 passed (R42's exact sentence, code-only (ZS), per-customer memory, pricing picks the next airline)
- Review: the negation binds to the airline ("do not offer/use/quote/book <airline>", "exclude/avoid/without/ohne/kein <airline>", a code only in brackets), remembered per customer only when the mail says future/any of our inquiries; no false positives on "we do not mind which airline", "nicht festgelegt", "avoid delays". Re-quote answers never fire on revised/new/instead/without/but/as well/also/valid/express (reviewer's five cases). Agent 368, backend 74.
- Review: for a DG quote the document ack and the quote recap say "I'll book it as soon as the Shipper's Declaration and the safety data sheet arrive, unless you tell me to wait" (matches DOCS_BOOK); non-DG keeps "won't book until you confirm".
