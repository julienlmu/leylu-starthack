# Submission checklist (Sun 22 Nov)

## Deadlines and where
| When (Berlin) | What |
|---|---|
| 12:00 | Hack League app submission form opens. **Submit a first version right away**, then keep editing |
| 12:45 | Form locks, hacking ends. Whatever is saved counts. One submission per team; any member can edit |
| 13:15–14:45 | Challenge pitch in **room 1180** (5U AI): 3 min pitch, 2 min Q&A, 1 min buffer. Be there before 13:15 |
| 15:30 | Top 3 per challenge announced, Main Stage. Challenge winner pitches again in the pitch battle |
| 16:45 | Overall winner |

5U did not publish an earlier deadline of its own (not in the kit, slides or deep-dive). The 5U board keeps scoring
until it is frozen (`frozen_at` on `/v1/board`): keep the live agent running until then.

5U's final judging (top teams): pitch, UI (CRM, quote dashboard, agent session view), code base, together with the
board score. Consistency over the whole run counts.

## What goes in the form (the form lists what it needs; have these ready)
- [ ] Project name: **Leylü, the night-shift freight forwarder**
- [ ] Short description (below)
- [ ] Repo link: https://github.com/julienlmu/leyl--starthack (check it is visible to the jury, or add 5U as collaborators)
- [ ] Pitch deck (export the deck as PDF or PPTX)
- [ ] Demo video (≤ 3 min, silent with captions, `pitch/DEMO_VIDEO.md`), in case the Wi-Fi drops during the live demo too
- [ ] Final numbers from `/v1/board` at ~12:00 into the deck results slide and README

## Short description (paste)
Leylü is an AI freight forwarder that ran live for 24 hours on 5U's mailbox. Every 6 minutes a customer asks for an
air-freight quote, in any language. Leylü routes the mail with plain rules, reads it with one tiny LLM call, asks the
airlines and truckers in parallel, prices everything in tested code and replies with one all-in quote in about 40
seconds. It books when the customer accepts, answers tracking questions from its own CRM, and catches 5U's traps:
lookalike senders, imports, price-match requests, portal outages and surges, multi-shipment mails, cancellations and
missing data. Across 189 requests it booked 130, at a total LLM cost of $0.085 (about $0.0005 per request).
A live Sessions UI shows every step and cost per mail and lets a person pause and step in.

## On stage
- Have the Sessions UI open before it's our turn; the video is the backup
- Q&A answers: `pitch/PITCH.md` → "Q&A prep"
