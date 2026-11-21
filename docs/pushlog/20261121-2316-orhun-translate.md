# Customer mails in languages without a template are translated (R74 wrong_language)
- Who: Orhun
- Branch: orhun/translate
- What changed: agent/templates.py localize(): when rfq.language has no template (zh, ja, ko, ru, ar, pl, …), quote/booking/confirmation/pickup-question/docs-ack mails are translated by one gateway call (gpt-6-luna); every amount and BK/R-/TRK- reference must appear unchanged, else the English mail goes out. TRANSLATE=off switches it off.
- How verified: agent 1408 passed; live call zh: 2.6 s, amount EUR 2,099.47 and airline/airport codes kept
- Non-English mails write weights without the thousands comma ("1497 kg"; R73 French "1,497 kg"); amounts unchanged.
