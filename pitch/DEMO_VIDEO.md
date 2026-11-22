# Demo video: silent screen recording with captions (≤ 3:00)

No voice-over: a silent screen recording, with one short caption per shot added afterwards (iMovie: Titles →
"Lower Third" or "Standard", 4–6 s each). The UI may still change before recording, so the shots name screens, not
buttons: session list, session detail, dashboard / scoreboard, 5U board.

Record on the Mac that runs the live agent, **read-only**: only look at the UI. Do not restart anything, and do not
press Pause or Intervene on a live session. QuickTime (File → New Screen Recording) or `Cmd+Shift+5`, 1920×1080.
Browser zoom 110–125 % so text reads on a projector. Move the mouse slowly; pause 2–3 s on each thing a caption names.

| # | Time | Shot (what is on screen) | Caption (on screen) |
|---|---|---|---|
| 1 | 0:00–0:10 | Deck cover slide | **It’s 2 a.m. An RFQ lands. Who answers?** |
| 2 | 0:10–0:25 | Session list: sessions arriving every 6 minutes, scroll through the night | **One mailbox. A new customer request every 6 minutes, for 24 hours.** |
| 3 | 0:25–1:00 | Session detail of a won session (or a live one between two rounds). Scroll the step trace slowly: routed → extracted → carriers asked → bids → priced → quote sent | **Rules route the mail. One tiny LLM call reads it. Code does every number.** then **Carriers asked in parallel. Quote out in ~40 s.** |
| 4 | 1:00–1:20 | Same session: the quote mail, then accepted → booked → tracking answer | **Customer says yes → booked once, by rate ID. “Where is it?” → answered from our CRM.** |
| 5 | 1:20–1:40 | Session detail **137** (Korean mail): the Korean request, our Korean reply, the “9 % cheaper” mail and our answer, then booked | **Any language, answered in the customer’s own. “9 % cheaper elsewhere?” Never below cost, still booked.** |
| 6 | 1:40–2:05 | Session details **188** (lookalike sender), **169** (import), **156** (two shipments in one mail), ~7 s each | **Fake sender: nothing sent.** · **Import: polite decline.** · **Two shipments: each priced on its own.** |
| 7 | 2:05–2:25 | Dashboard / scoreboard page | **189 requests · 130 booked · median reply 38 s · $0.085 LLM for the whole run** |
| 8 | 2:25–2:40 | 5U board (our row) | **#[_] of 14 teams** (fill in when recording) |
| 9 | 2:40–2:55 | Deck slide 7 (what’s next) | **At 2 a.m., our forwarder answers.** |

Total ≈ 2:55. If it runs long, shorten shot 2 first, then shot 6 to two sessions.

## Checklist before you hit record
- [ ] Do Not Disturb on; no `.env`, terminal or API key on screen
- [ ] Session list, dashboard and 5U board open in tabs, deck in a fourth (Present mode)
- [ ] Check sessions 137 / 188 / 169 / 156 still look right in the current UI
- [ ] Captions: one font, white on a dark band, bottom third, ≥ 4 s each
- [ ] Export MP4 (1080p) and upload to the Hack League form early (Wi-Fi gets busy around 12:30)
