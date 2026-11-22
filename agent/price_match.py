"""PRICE_MATCH (default on; off = a person, as COUNTER_OFFER did): haggling after our quote, answered by rules.

R111: "looks good, but another forwarder quoted 7% less, can you match?". Our quote is already a carrier's cost (no
margin on top), so the answer is the lowest real all-in we can get NOW: the request priced again with every bid the
session collected (air + pickup legs, portal, sheets: backend /api/price), cheapest option. Never below that cost.
- the best all-in is at or below what they ask (percent or amount) → we offer it;
- it is lower than our quote but above their ask → "can't go that low, the best I can do is Y";
- it is not lower than our quote → our quote is already the best price (held on every further ask).
The session's quote is re-pointed to the option offered (its rate ID / carrier), so a "yes" books exactly that.
One amount per mail (never their figure written back), English or German, else English. Rules only, no LLM.
After MAX_ROUNDS answers a person takes over.
"""

import os
import re

ON = os.environ.get("PRICE_MATCH", "on").lower() != "off"
MAX_ROUNDS = 3

_LESS = r"(?:less|lower|cheaper|under|below|off|discount|rabatt|günstiger|guenstiger|weniger|billiger|moins|menos|meno)"
PERCENT = re.compile(rf"(\d{{1,2}}(?:[.,]\d)?)\s?%\s?(?:\w+\s){{0,3}}?{_LESS}|{_LESS}\s(?:\w+\s){{0,3}}?(?:by\s|um\s)?"
                     rf"(\d{{1,2}}(?:[.,]\d)?)\s?%", re.I)
ASKS = re.compile(
    rf"\b(?:match|beat|price[- ]?match|best\s+(?:price|rate|offer)|better\s+(?:price|rate|offer)|lower\s+(?:price|rate)|"
    rf"(?:any|some)\s+(?:room|flexibility|discount)|can\s+you\s+do\s+(?:it\s+)?(?:cheaper|better|less|lower)|"
    rf"(?:cheaper|lower)\s+(?:quote|offer|price)|another\s+(?:forwarder|agent|carrier|provider|company)\s+(?:quoted|offered)|"
    rf"competitor|discount|too\s+(?:expensive|high)|negotia\w*|"
    rf"besten?\s+preis|günstiger|guenstiger|rabatt|nachlass|zu\s+teuer|mitbewerber|konkurrenz|"
    rf"meilleur\s+prix|moins\s+cher|mejor\s+precio|más\s+barato|miglior\s+prezzo|daha\s+ucuz|en\s+iyi\s+fiyat)\b|"
    rf"\d\s?%\s?(?:\w+\s){{0,3}}?{_LESS}", re.I)

TEXT = {
    "en": {"intro": "Thanks for letting me know. I've checked all our rates for this shipment again.",
           "again": "I've checked once more, and nothing has changed on our side.",
           "match": "I can offer it for {amount} all-in with {carrier}{days}.",
           "partly": "I can't go as low as {target}, but the best I can do is {amount} all-in with {carrier}{days}.",
           "floor": "{amount} all-in with {carrier}{days} is already the best price I can offer for this shipment.",
           "close": "Just reply yes and I'll book it.", "days": ", about {n} days in transit",
           "pct": "{p} % less", "your": "your target price"},
    "de": {"intro": "Danke für den Hinweis. Ich habe alle unsere Raten für diese Sendung noch einmal geprüft.",
           "again": "Ich habe es noch einmal geprüft, auf unserer Seite hat sich nichts geändert.",
           "match": "Ich kann sie Ihnen für {amount} all-in mit {carrier}{days} anbieten.",
           "partly": "{target} schaffe ich leider nicht, aber mein bester Preis ist {amount} all-in mit {carrier}{days}.",
           "floor": "{amount} all-in mit {carrier}{days} ist bereits der beste Preis, den ich für diese Sendung "
                    "anbieten kann.",
           "close": "Ein kurzes Ja genügt und ich buche es.", "days": ", ca. {n} Tage Laufzeit",
           "pct": "{p} % weniger", "your": "Ihren Zielpreis"},
}


def asks(text: str) -> bool:
    return ON and bool(ASKS.search(text or ""))


def percent(text: str) -> float | None:
    found = PERCENT.search(text or "")
    if not found:
        return None
    value = float((found.group(1) or found.group(2)).replace(",", "."))
    return value if 0 < value < 60 else None


def target(text: str, quote: dict, other_price) -> tuple[float | None, str | None]:
    """(the all-in they ask for, how to name it without a second amount) or (None, None) for "best price?"."""
    total = float(quote.get("total") or 0)
    if (p := percent(text)) and total:
        return round(total * (1 - p / 100), 2), "pct:" + (f"{p:g}")
    if (amount := other_price(text, quote)) and amount < total:
        return amount, "your"
    return None, None


def best(result: dict, quote: dict) -> dict | None:
    """The cheapest priced option in the quote's currency (ties: faster)."""
    currency = (quote.get("currency") or "EUR").upper()
    options = [o for o in result.get("options") or [] if o.get("total") is not None
               and (o.get("currency") or "EUR").upper() == currency]
    return min(options, key=lambda o: (float(o["total"]), o.get("transit_days") or 99)) if options else None


def reply_lines(lang: str, quote: dict, offer: dict, wanted: float | None, named: str | None, rounds: int,
                money) -> tuple[list[str], str]:
    """(mail lines, which case) for the offer. `money` formats one amount."""
    t = TEXT[lang if lang in TEXT else "en"]
    days = t["days"].format(n=max(1, round(float(offer["transit_days"])))) if offer.get("transit_days") else ""
    fill = {"amount": money(offer), "carrier": offer.get("carrier") or "our airline", "days": days}
    lower = float(offer["total"]) < float(quote["total"]) - 0.005
    if wanted is not None and float(offer["total"]) <= wanted + 0.005:
        case = "match"
    elif lower:
        case = "partly"
        fill["target"] = t["pct"].format(p=named[4:]) if (named or "").startswith("pct:") else t["your"]
    else:
        case = "floor"
    if case == "partly" and wanted is None:
        case = "match"  # "best price?": the lower all-in, no target to fall short of
    intro = t["again"] if rounds and case == "floor" else t["intro"]
    return [intro, t[case].format(**fill), t["close"]], case
