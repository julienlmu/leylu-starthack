**Task:** humanity awards (the jury's +10) · **Agent:** Claude Code

# Quote mail: answer the customer's question, match their tone, one detail, full sign-off (MAIL_HUMAN)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/human-mail
- Why: we lead on accepted quotes but trail google by 11 awards and start-milan by 24 (~10 points each). R79 asked for the arrival and the short mail dropped it.
- What changed (`agent/short_mail.py`, code only, no LLM call). `MAIL_HUMAN` defaults to on; `off` gives the mail as before:
  - The customer's question gets one clause (en/de):
    - Earliest arrival: from the ready date, truck and flight (quote_style._dates).
    - Drop-off: at the airline's terminal at the origin airport, port-to-port only.
    - AWB: "comes with the booking confirmation".
  - Formality:
    - German "Sie" → "Guten Tag Klaus Hofmann," (no Herr/Frau guess); German "du" → "Hallo Klaus," and "Danke dir".
    - Formal English ("Dear", "Yours sincerely") → "Dear Sara Lindqvist,".
  - One detail from their mail:
    - Commodity: "5 pieces of automotive sensors", en, letters only, so no digit reaches the gate's one-amount check.
    - Pickup town: "pickup in Giessen included".
  - Full closing sentence plus "Lena Hartmann, Leylü Air Freight":
    - en: "Thanks again for thinking of us."
    - de: "Vielen Dank für Ihre Anfrage und viele Grüße".
    - Other languages and the booked/confirmed mails keep their closing word and get the full name.
- Untouched: the amount string, airline, airport codes and the reply line ("just reply yes and I'll book it", the no-full-stop imperfection). The booking and confirmation wording is unchanged too, and gate.finish still passes.
- Tests:
  - agent 1909 passed; backend 231.
  - 4 new tests in test_short_mail.py: R79's mail, German Sie/du with AWB and drop-off, no digits from the commodity, and MAIL_HUMAN=off.
- New env vars: MAIL_HUMAN (default on). No packages.
- Julien: this builds on your short_mail (#190), so please check that the extra clause fits your "2-4 short lines" idea.
