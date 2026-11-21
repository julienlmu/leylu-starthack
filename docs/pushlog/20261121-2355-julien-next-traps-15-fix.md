# next-traps-15-fix: #191's trap variants merged on main, narrowed where they misfired
On top of Orhun's #191 (counter-offers, weekday deadlines, feet/grams, airport spellings, DG vehicles, reply language).
- Who: Julien (tool: Claude Code)
- Branch: julien/next-traps-15-fix
- What changed:
  - Merged main: main's ACCEPT/CONFIRM/DECLINE (#193) and reply language (#189: REPLY_IN, `reply_language`, `mail_language`) kept as they are. Counter-offers sit on top: another amount than our total, or haggling words ("our budget is 2k", "can you do EUR 1,800?", "beat"), never book (even if the model says accept) and never get our quote again from QUOTE_ANSWERS / CONFIRM_ANSWERS / DG papers; a person answers. Also with no stored total.
  - Reply language: #191's script rule (CJK/Arabic/Cyrillic body → that language; model's CJK code with no such script in the body → en) only when the customer asked for no language, and the model's reading stays when it is a language of that script (uk, fa, ja kanji). No duplicate schema field.
  - Narrowed: airport spellings take a dropped/added/swapped letter only ("Homburg" was read as HAM in 13 real mails); a lone `'` after dims is no feet; "80 g/m²" is no gram weight; EV chargers / models / toys are no DG vehicles.
- Files touched: agent/booking_agent.py, extract.py, airports.py, units.py, gate.py, test_next_traps_15.py
- Contract/API changes: none
- New env vars / packages: from #191: COUNTER_OFFER, WEEKDAY_DEADLINE, FEET_GRAMS, AIRPORT_TYPOS, DG_VEHICLES, LANGUAGE_RULES (all default on, `off` = before)
- How verified: `NEXT_TRAPS_PORT=8791 make check` exit 0 (agent 1869 passed / 22 xfailed, backend 222 passed, eslint + tsc clean); extract eval replay 25/25 ok, 0 wrong. Old (main @ 4615458) vs new over 467 real mails + 58 raw replays (mailtest, latest*, new*, day1, rfq_cases, traps): 0 changes in deadline, budget, DG, units, airports, script language; no customer reply has an amount or haggling word (only carrier bids, which never reach read_intent).
- Known issues / TODO: "scale model motorcycles" still reads as DG (a hold, safe side).
- Heads-up for teammates: `read_intent(body, quote)` takes the open quote now; `booking_agent.counter_offer(text, quote)` is the one check.
