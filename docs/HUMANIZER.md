# HUMANIZER.md: should we use blader/humanizer? (for Orhun)

> From Batu's link: https://github.com/blader/humanizer · Ulas, Sat ~18:15.

## What it is
An agent skill (Claude Code, Codex; MIT licence) that rewrites AI-sounding prose so it reads like a person wrote it, without changing what it says. It checks 26 patterns from Wikipedia's "Signs of AI writing", e.g. "not X but Y", one-line closers ("Let that sink in."), sayings that sound deep, staged run-ups ("Here's the thing."), cheerful filler. Every rewrite is an LLM call.

## Verdict: use it once, offline, on our templates. Not in the live agent.
- **Not at runtime:** our customer mails are hand-written templates in `agent/templates.py`, filled by code. A humanizer call per mail would add LLM cost (40 cost points per quote are at stake), add seconds to every quote, and could change or add numbers (the "one amount per mail" rule).
- **Offline it's free and safe:** run it once over the template strings, keep the result as templates. Zero cost per quote, same rules.
- **Worth it?** Humanity is one +10 jury award (the most human accepted email) plus final-jury criterion 4. Lower priority than accuracy and speed fixes, but a 15-minute job.

## How (for Orhun's Claude)
1. Install: `/plugin marketplace add blader/humanizer` then `/plugin install humanizer@humanizer` (Claude Code 2.1.142+).
2. Run `/humanizer` on the **English** strings in `agent/templates.py` (`T["en"]`: thanks, offer, price, cta, dg, booked, confirmed, plus `tracking_text`, `tracking_unknown_text`, `bid_request_text`). Likely candidates: cheerful openers like "Great, it's booked!" and "Good news:".
3. Keep every `{placeholder}` exactly, keep **no digits** in the text, keep exactly one amount (`{amount}`) in the quote, keep the bid-request reply format (`Total: … / Transit: … / Rate ID: …`) because `bids.parse_bid` reads it.
4. Carry the same changes into the other 7 languages by hand; the skill is tuned for English.
5. `cd agent && uv run pytest -q` (the template tests check one amount per mail and every language).
6. Deploy between rounds.
