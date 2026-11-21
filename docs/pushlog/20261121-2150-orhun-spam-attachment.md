# Spam filter: an attachment protects unless it is an executable or archive (review of #150)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/spam-attachment
- What changed: agent/router.py is_spam: a mail with any attachment that isn't .exe/.zip/.rar/.js/.html/.htm/.scr/.iso/.bat/.cmd/.vbs is never spam ("Please find our inquiry attached. Payment terms: wire transfer within 30 days." + request.pdf was dropped on main); risky attachments still go through the phishing check.
- How verified: agent test_spam 6 passed (the review's two sentences with .pdf and .xlsx stay RFQs, an overdue invoice .zip is spam; Ulas's test now uses inv.zip). Full agent suite: 1242 passed, 1 failure that is already on main without this change (test_cargo_price_sweep scanned-attachment lambda signature).
