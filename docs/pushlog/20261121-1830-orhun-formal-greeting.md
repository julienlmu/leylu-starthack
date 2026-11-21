# Quote wording: a formal customer gets "Dear Jonas Kessler," (R25)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/formal-greeting
- What changed:
  - agent/quote_style.py: "Dear …" / "Sehr geehrte …" / "Good morning" at the start, or "Yours sincerely" / "Mit freundlichen Grüßen", means a formal mail: the quote opens "Dear <full name>," (no Mr/Ms, we don't guess gender), "Hello," without a name; casual mails keep "Hi Jonas,"
- Files touched: agent/quote_style.py, agent/test_quote_style.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: agent 337 passed (18 xfailed), backend 69 passed
- Heads-up for teammates: none
