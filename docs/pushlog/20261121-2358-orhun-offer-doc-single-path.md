**Task:** R76/R77 no_pdf_offer · **Agent:** Claude Code

# Offer file in the asked format, one path (offer_doc); already live since 23:46:54
- Who: Orhun (tool: Claude Code)
- Branch: orhun/pdf-offer (main merged in, nothing replaced)
- **Julien: this is already live** (1fdb59f restarted at 23:46:54, Orhun's call: "direk şimdi canlıya al"). R76 and R77 were both rejected `no_pdf_offer` (~110 points each), and the ask now comes every round. This PR brings the live code to main and removes the duplicate.
- What changed:
  - `agent/offer_doc.py` is the single path for the offer file. It reads the format the RFQ asks for (PDF, Word/DOCX, Excel/XLSX, CSV, TXT, ZIP, in any of our languages) and attaches that file. A "fill in our form" request goes to a person. A requested folder or file name ("put it in a folder quotes, name the file Offer Lima.pdf") is applied with safe names: no `..`, no absolute paths, `[^\w.-]` becomes `_`.
  - `_reply_quote`: the format asked for, else a PDF while `PDF_OFFER=always` (Julien's #200 default is kept). If the offer file can't be built, the mail's text as a PDF (#200). If that fails too, the mail goes out alone. A 5U refusal still resends without the attachment (#200/#202 `inbox.py`, main's version).
  - `offer_doc.pdf` now uses `pdf_offer.build`, so the agent has one PDF writer, the one checked with pdfplumber.
  - Removed `agent/quote_pdf.py` (#199) and its test: they duplicated `offer_doc`. The pdfplumber check now runs on `offer_doc.attachment("pdf", …)`: one amount, umlauts, carrier.
- Tests: agent 1895 passed / 22 xfailed; backend 229 passed. Dry-run on R79's real quote: `Leylu-quote-S-79.pdf`, application/pdf, EUR 1,533.69.
- New env vars / packages: none (PDF_OFFER as before).
- Rollback: 239cefe (before the offer file), or `PDF_OFFER=off` (only explicit asks attach).
