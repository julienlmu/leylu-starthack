# HUMANIZER.md: should we use blader/humanizer? (for Orhun)

> From Batu's link: https://github.com/blader/humanizer · Ulas, Sat ~18:15.

## What it is
An agent skill (Claude Code, Codex; MIT licence) that rewrites AI-sounding prose so it reads like a person wrote it, without changing what it says. It checks 26 patterns from Wikipedia's "Signs of AI writing", e.g. "not X but Y", one-line closers ("Let that sink in."), sayings that sound deep, staged run-ups ("Here's the thing."), cheerful filler. Every rewrite is an LLM call.

## Verdict: use it once, offline, on our templates. Not in the live agent.
- **Not at runtime:** our customer mails are hand-written templates in `agent/templates.py`, filled by code. A humanizer call per mail would add LLM cost (40 cost points per quote are at stake), add seconds to every quote, and could change or add numbers (the "one amount per mail" rule).
- **Offline it's free and safe:** run it once over the template strings, keep the result as templates. Zero cost per quote, same rules.
- **Worth it?** Humanity is one +10 jury award (the most human accepted email) plus final-jury criterion 4. Lower priority than accuracy and speed fixes, but a 15-minute job.

## Better than any tool: answer *this* customer (free, no extra LLM call)
What reads human is a mail that obviously answers this request. The extraction already gives us the details:
1. **Echo their specifics:** pickup town, goods, destination, ready day ("on Tuesday" / month name: no digits, one amount per mail).
2. **Answer what they asked:** "please arrange the truck" → "we'll arrange the truck from your site"; asked for cheapest → say it's the cheapest we found.
3. **Match formality, not style:** du/Sie, tu/vous, first name vs. "Herr Weber" (one more field in the same extraction call). Never copy their typos, slang, caps, rudeness or broken grammar: whatever they write, we reply polite, clear and simple.
4. **One real person signs** every mail, same name.
5. **A native speaker reads each language once** (Ulas: TR/DE/EN; the machine-translated fr/es/it/nl/pt need it most).

## Training a model on example mails: no
- 5U's gateway only serves its listed models; a fine-tuned model most likely can't be called there, and calls outside the gateway don't count.
- It puts an LLM back into every mail: cost points, latency, and the risk of a second number in the quote.
- Hours of work for one +10 jury award.

## Cheap version: learn from the mails we already have (offline, once)
Our mailbox has 120+ mails written by 5U's customer and carrier agents: the register the jury designed. Have Claude read a sample once and note the **structure** (greeting, length, how they get to the point, sign-off). Rewrite the templates in that register. Copy structure and tone, never individual quirks or errors (see point 3 above). Zero cost per mail.

## Later: learn from the jury's humanity points
So far every +10 we got is a **tracking** bonus; the board's `human` column is still 0 for all teams. Once the jury starts awarding humanity points, the board shows which team won it (the watcher pushes it for our neighbours). If we win one, keep that mail's wording as the reference; if a neighbour wins, compare their tone with ours.

## How (for Orhun's Claude)
1. Install: `/plugin marketplace add blader/humanizer` then `/plugin install humanizer@humanizer` (Claude Code 2.1.142+).
2. Run `/humanizer` on the **English** strings in `agent/templates.py` (`T["en"]`: thanks, offer, price, cta, dg, booked, confirmed, plus `tracking_text`, `tracking_unknown_text`, `bid_request_text`). Likely candidates: cheerful openers like "Great, it's booked!" and "Good news:".
3. Keep every `{placeholder}` exactly, keep **no digits** in the text, keep exactly one amount (`{amount}`) in the quote, keep the bid-request reply format (`Total: … / Transit: … / Rate ID: …`) because `bids.parse_bid` reads it.
4. Carry the same changes into the other 7 languages by hand; the skill is tuned for English.
5. `cd agent && uv run pytest -q` (the template tests check one amount per mail and every language).
6. Deploy between rounds.
