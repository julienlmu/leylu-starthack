# Demo video: script and shot list (≤ 3:00)

Record on the Mac that runs the live agent, **read-only**: only look at the Sessions UI (http://localhost:3000) and the
dashboard. Do not restart anything, do not press Pause or Intervene on a live session, and record between two rounds
if you want a live RFQ on screen. Screen recorder: QuickTime (File → New Screen Recording) or `Cmd+Shift+5`,
1920×1080, mic on. Browser zoom 110–125 % so text reads on a projector.

Session numbers below are from the CRM export at 10:15 Berlin; they all exist in the live UI.

| # | Time | Shot (what is on screen) | Voice-over (say roughly this) |
|---|---|---|---|
| 1 | 0:00–0:15 | Deck cover slide ("It's 2 a.m. An RFQ lands. Who answers?") | "It's 2 a.m. A customer wants a price for air freight. A human forwarder is asleep. Ours isn't." |
| 2 | 0:15–0:30 | Deck slide 2 (problem) | "Forwarding runs on email: rate sheets, a portal, five carriers. Too expensive, too slow or one missed detail, and the deal is gone." |
| 3 | 0:30–1:05 | Sessions UI, list view, then open the newest **won** session (or a live one between rounds). Scroll the event trace: routed (rules, no LLM) → extracted (cost shown) → carriers asked → bids in → priced → quote sent | "Every mail becomes a session. The router is plain rules. One tiny model call reads the fields, code does every number. Carriers are asked in parallel, and the quote goes out in about 40 seconds." |
| 4 | 1:05–1:25 | Same session: open the quote mail, then the "accepted" → "booked" → tracking answer events | "The customer says yes, we book by rate ID exactly once, and 'where is my cargo?' is answered from our own CRM." |
| 5 | 1:25–1:45 | Session **137** (Korean mail, FRA → RUH): show the Korean mail and our reply in Korean, then the customer's "another forwarder is 9 % cheaper" and our "price match asked (floor)" reply, then "booked" | "Any language, replied in the customer's own. When the customer says a competitor is 9 % cheaper, we re-check every real bid and never go below cost. Here our price was already the floor, we said so, and the customer booked anyway." |
| 6 | 1:45–2:05 | Session **188** (lookalike sender, closed silently), then **169** (import declined), then **156** (two shipments in one mail) | "5U set traps every hour. A fake sender that looks like a customer: we send nothing. An import: we decline. Two shipments in one mail: each one priced on its own." |
| 7 | 2:05–2:25 | Dashboard page: won / lost, response-time chart, cost per quote | "Eighteen hours live: 189 requests, 130 booked, median reply 38 seconds, eight and a half cents of LLM for the whole night." |
| 8 | 2:25–2:40 | Sessions UI, "needs a person" filter, open one flagged session and show the Pause / Intervene bar (don't press it) | "When something is truly unusual, it lands here, and a person can pause and answer by hand." |
| 9 | 2:40–2:55 | Deck slide 7 (what's next) | "Next: learn margins per lane from won and lost quotes, and plug into real carrier APIs. At 2 a.m., our forwarder answers." |

Total ≈ 2:55. If it runs long, cut shot 8 first, then shot 2.

## Checklist before you hit record
- [ ] Notifications off (Do Not Disturb), no `.env`, terminal or API key visible on screen
- [ ] Sessions UI and dashboard open in two tabs, deck open in a third (Present mode)
- [ ] Mail bodies show customer names from 5U's fictional companies only (fine to show)
- [ ] Practise once with a timer; the jury cut-off is strict
- [ ] Export as MP4 (≤ 1080p), upload to the Hack League form early (Wi-Fi gets busy around 12:30)
