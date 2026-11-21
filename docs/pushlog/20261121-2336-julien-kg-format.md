# kg-format: no English thousands comma in non-English mails (R73)
- Who: Julien (tool: Claude Code)
- Branch: julien/kg-format
- What changed: agent/short_mail.py wrote "1,674 kg" in every language; in German/French/... the comma is the decimal mark (1,674 kg = 1.674 kg). English keeps "1,674 kg", every other language "1674 kg" (the point Orhun found in R73, #184 5137f6d, applied to the short mails on main)
- Files touched: agent/short_mail.py, agent/test_short_mail.py
- Contract/API changes: none
- New env vars / packages: none
- How verified: make check green (agent 1757 passed / 17 xfailed, backend 222); test: en 1,674 kg, de/fr/pl/ja 1674 kg
- Known issues / TODO: the amount stays "EUR 2,345.67" in every language on purpose (the gate and 5U read that form)
- Heads-up for teammates: none
