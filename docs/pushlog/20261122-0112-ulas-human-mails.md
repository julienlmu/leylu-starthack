# HUMAN_MAILS: in-between mail style for humanity points
- Who: Ulas (tool: Claude Code)
- Branch: ulas/human-mails
- What changed: docs/HUMAN_MAILS.md (humanity data: style a won 5 rounds, short 0 since 22:41; how to build an in-between style from humanizer.py + short_mail.py; slot template; 14 target mails; the goods_phrase piece-count bug)
- Files touched: docs/HUMAN_MAILS.md, docs/pushlog/
- Contract/API changes: none
- New env vars / packages: none (proposes QUOTE_STYLE=between)
- How verified: humanity rounds from /v1/board/me points.humanity; style switch times from git log of agent/quote_style.py; docs only
- Known issues / TODO: none
- Heads-up for teammates: Julien, please build QUOTE_STYLE=between from this
