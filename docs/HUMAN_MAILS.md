# HUMAN_MAILS.md: an "in-between" mail style to win humanity points again (for Julien)

> Ulas, Sun ~00:40. Data from `/v1/board/me` (`points.humanity`): we won humanity in rounds 13, 19 (old templates), **55, 57, 58, 64, 74 while `QUOTE_STYLE=a` was the default (18:32-22:41)**, and **0 times in ~16 rounds since `short` became the default at 22:41**. Humanity is roughly one winner per round (101 points over 90 rounds; START Milan 31, Google 16, AEIOU 11, makeanothermd 10, us 7).
> Read: "a" won because it clearly reacted to *this* customer (small talk returned, goods, town, days); "short" is so terse it reads like a bot; "a" is too long and stiff. This style is in between: **short and casual like `short`, personal like `a`.** Written human-first: the human mail IS the template, code fills the slots, no LLM writes or rewrites it.

## What to change in the existing code
Add it as a new style (e.g. `QUOTE_STYLE=between`, default) so we can switch back without a deploy. Build it from what exists:
- **From `humanizer.py` (style a), keep:** `tone()` / small-talk reply (one short line, only if the customer wrote some), `greeting()` incl. the "title only if the customer wrote it" rule, `pickup_town()`, `_city()` (city names instead of codes), `_day()` (day names), the goods phrase, DG detection.
- **From `short_mail.py`, keep:** length (3-5 lines), casual wording, the simple sign-off, every-language mechanism (translated templates with placeholders, facts filled by code).
- **Drop from "a":** "I've put together a quote for your request", "the most economical option at the moment", "Your all-in price is …", "The only proviso is space on the flight, which the airline confirms when we book", full "Wednesday 25 November … Thursday 26 November … Sunday 29 November" sentences, "Reply to this email whenever you're ready", the 3-line signature block.
- **Fix the "a" bug:** `goods_phrase` turns pieces into items: "your **four maintenance spray cans** (855 kg)", "your **eight spare parts** (911 kg)". Always "{count} {crates/pallets/boxes/pieces} of {goods}"; one piece = "the box" / "your crate", never "your 1 piece".
- **Never:** ISO dates (also in tracking: "handover is planned for 2026-11-24" → "handover is monday"), mixing du/Sie in German, "your packing list declares" unless the DG info really came from a packing list.
- **Keep:** exactly one amount per quote (written by code), the DG papers request, the gate checks, reply in the customer's (or requested) language.

## Slot template (quote)
```
Hi {first name},

{small-talk reply, only if they wrote some} For your {count} {pieces word} of {goods} I can do {airline short name} from {origin city} to {destination city} for {amount} all in{, pickup in {town} included}. We'd collect {day} and it should land around {day}.
{DG line, only if DG}
just reply and I'll book it, space gets confirmed then.

cheers,
Lena
```
Formal customer ("Dear Sir or Madam", full signature with title): "Hello Ms {surname}," / "thank you for your request." / "best regards," — title only if they wrote it, else "Hello {first} {last},".

## Target mails (tune the wording, keep the shape)

**1. Plain request, no small talk, airport to airport**
> Hi Anna,
>
> for your 2 pallets of machine parts I can do Solace from Frankfurt to New York for EUR 1,308.21 all in. They'd fly monday and land around wednesday.
>
> just reply and I'll book it, space gets confirmed then.
>
> cheers,
> Lena

**2. Customer chatted first, door-to-port**
> Hi Klaus,
>
> all good here, thanks, hope yours is too! For your 3 crates of adhesives I can do Juniper from Frankfurt to São Paulo for EUR 2,481.50 all in, pickup in Bad Homburg included. We'd collect wednesday and it should land around sunday.
>
> just reply and I'll book it, space gets confirmed then.
>
> cheers,
> Lena

**3. Fastest asked**
> Hi Tom,
>
> fastest I've got for your 4 boxes of spare parts is Lumen, Frankfurt to Chicago, EUR 1,874.40 all in. Flies tomorrow, lands thursday.
>
> reply and I'll lock it in, space gets confirmed when I book.
>
> cheers,
> Lena

**4. Formal customer**
> Hello Ms Meyer,
>
> thank you for your request. For your 8 crates of spare parts for packaging machines I can offer Himalaya Bridge from Frankfurt to Ulaanbaatar for EUR 4,890.00 all in, collection in Wiesbaden included. We'd collect friday and it should arrive around wednesday.
>
> just reply and I'll book it, space is confirmed at booking.
>
> best regards,
> Lena

**5. Dangerous goods**
> Hi Sara,
>
> for your 4 crates of spray cans I can do Aurelia from Hamburg to Toronto for EUR 3,120.00 all in, pickup in Lüneburg included. We'd collect thursday and it should land around sunday.
>
> these are DG so I'll need the shipper's declaration and the MSDS from you before pickup.
>
> reply and I'll book it.
>
> cheers,
> Lena

**6. One box, PO reference**
> Hi Mike,
>
> re your PO-4711: the box goes with Xenon from Frankfurt to New York for USD 398.00 all in, about 3 days.
>
> just say yes and I'll book it.
>
> cheers,
> Lena

**7. German, informal (customer wrote "Hallo" and signed with first name)**
> Hallo Jürgen,
>
> für deine 2 Paletten Maschinenteile kann ich Borealis von München nach Chicago anbieten, EUR 2,215.90 all-in, Abholung in München inklusive. Wir holen am Dienstag ab, Ankunft etwa Donnerstag.
>
> kurzes Ja reicht, dann buche ich.
>
> viele Grüße
> Lena

**8. Booking confirmation**
> Hi Anna,
>
> done, it's booked with Solace, ref BK-1A2B3C4D. I'll let you know as soon as they confirm.
>
> cheers,
> Lena

**9. Airline confirmed**
> Hi Anna,
>
> Solace just confirmed BK-1A2B3C4D, so you're all set for monday.
>
> cheers,
> Lena

**10. Tracking, booked, not flown yet** (must contain the right status AND the BK reference: 5 points each)
> Hi Anna,
>
> BK-1A2B3C4D is booked and confirmed by Solace, it hasn't left yet. Handover at Frankfurt is monday, should land in New York around wednesday.
>
> I'll keep you posted.
>
> cheers,
> Lena

**11. Tracking, no matching reference**
> Hi,
>
> I couldn't find that one on our side. Could you send me the booking ref (starts with BK-)? Then I'll check right away.
>
> cheers,
> Lena

**12. Price changed before booking (reconfirm; the only mail that states the new price)**
> Hi Klaus,
>
> quick one before I book: Juniper's price changed since my quote, it's now EUR 2,530.00 all in. Still want me to go ahead?
>
> cheers,
> Lena

**13. Pickup postcode missing** (only where the team accepts a non-quote first reply)
> Hi Sara,
>
> happy to quote this, just need the postcode of your pickup address so I can price the truck. Send it over and you'll have the price right away.
>
> cheers,
> Lena

**14. Customer declined**
> Hi Tom,
>
> no worries, thanks for letting me know. Happy to quote the next one.
>
> cheers,
> Lena

## How to test it
Render 10 real RFQs from `agent/evals/real_rfqs_day1.json` in `between` and compare with these targets; run the template/humanizer tests and the gate's one-amount checks; deploy between rounds; then watch our `human` count on the board for an hour (the watcher pushes neighbours' humanity wins; ours is in `/v1/board/me` `points.humanity`).
