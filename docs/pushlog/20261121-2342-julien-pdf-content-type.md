# pdf-content-type: the quote PDF is sent as application/pdf
- Who: Julien (tool: Claude Code)
- Branch: julien/pdf-content-type
- What changed: 5U's OpenAPI AttachmentIn = {filename, content_type (default application/octet-stream), content_base64}; #200 sent no content_type, so the PDF would arrive as an untyped file (maybe not "a PDF offer" for the no_pdf_offer check). Now content_type "application/pdf" (Orhun's #199 had it right)
- Files touched: agent/rfq_agent.py, agent/test_pdf_offer.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: make check green; the test asserts content_type
- Known issues / TODO: none
- Heads-up for teammates: none
