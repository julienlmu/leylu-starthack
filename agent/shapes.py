"""RFQ shapes a single all-in quote must react to (rules on the mail text, no LLM call).

Before pricing (rfq_agent.handle_rfq, `before_pricing`):
- MULTI_SHIPMENT: two shipments in one RFQ (two destinations, or consignments that fly apart: "two separate
  consignments", two ready dates). One combined price is wrong either way, so a person answers: added to `missing`,
  which hands the RFQ over without a quote (no fallback quote either).
- INCOTERM_PICKUP: EXW / ex works / ab Werk, or FCA at the customer's site, with a German postcode or a pickup-zone town
  next to it: door-to-port (a trucker to the zone's airport), never airport-to-airport (round 1's too_low). FCA with
  only a town ("FCA Frankfurt") is the handover at that airport and stays airport-to-airport.

In the quote gate (gate.review section 7, `gate_sentences`), one sentence without digits each:
- DESTINATION_DELIVERY: DDP / DAP / door-to-door / delivery to the consignee: we price to the destination airport, so
  the quote says that delivery, customs and duties at destination are not included (never silently port-to-port).
- BOTH_ASKS: "cheapest and fastest": the quote follows the ask the backend and the gate picked and names the option
  that wins the other ask in words, never with a second amount.
Each `<FLAG>=off` (env + restart) restores the behaviour before.
"""

import os
import re

from airports import CITY, known
from extract import AREAS, CHEAP_WORDS, FAST_WORDS, NOT_ASK, NOT_FAST, SIGN_OFF, _plain, city_zone, zone_airport
from inbox import latest_text

MULTI_SHIPMENT = os.environ.get("MULTI_SHIPMENT", "on").lower() != "off"
INCOTERM_PICKUP = os.environ.get("INCOTERM_PICKUP", "on").lower() != "off"
DESTINATION_DELIVERY = os.environ.get("DESTINATION_DELIVERY", "on").lower() != "off"
BOTH_ASKS = os.environ.get("BOTH_ASKS", "on").lower() != "off"

ORIGINS = {"CGN", "DUS", "FRA", "HAM", "MUC", "STR"}


def _request(mail: dict) -> str:
    """The customer's own words: the newest mail, without the signature (a company address is no pickup)."""
    return SIGN_OFF.split(latest_text(mail.get("body") or ""), 1)[0]


# ---- several shipments ---------------------------------------------------------------------------------------------

WEIGHT = re.compile(r"\d[\d.,]*\s*(?:kgs?|kilos?|lbs?|pounds?|t|tonnes?)\b", re.I)
VIA = re.compile(r"\b(?:via|über|ueber|through|over|transit(?:ing)?(?:\s+(?:in|at|via))?|routing)\s+$", re.I)
SEPARATE = re.compile(
    r"\b(?:two|three|four|2|3|4|zwei|drei|vier|deux|trois|dos|tres|due)\s+(?:separate\s+|different\s+|individual\s+|"
    r"getrennte\s+|einzelne\s+|verschiedene\s+)?(?:shipments|consignments|sendungen|lieferungen|envois|envíos|"
    r"spedizioni)\b(?!\s+(?:a|per|each|every|pro|im|this|next|last|diesen|nächsten|letzten)\s+(?:month|week|year|day|"
    r"quarter|monat|woche|jahr|quartal))"
    r"(?!\s+(?:monthly|weekly|yearly|annually|monatlich|wöchentlich))"
    r"|\bseparate\s+(?:shipments|consignments|bookings|AWBs?|air\s*waybills?)\b"
    r"|\b(?:quote|price|ship|send|fly|book)\w*\s+(?:each|both|the\s+two|all)\s+(?:of\s+the\s+)?(?:lots?|shipments?|"
    r"consignments?|deliveries|orders?|sendungen|partien)\s+separately\b"
    r"|\b(?:each|both)\s+(?:shipment|lot|consignment|one)s?\s+(?:\w+\s+){0,3}(?:separately|on\s+(?:its|their)\s+own)\b"
    r"|\bgetrennt\w*\s+(?:versenden|verschicken|anbieten|fliegen|sendungen|angebote?)\b"
    r"|\bseparat\w*\s+(?:versenden|verschicken|anbieten|sendungen)\b", re.I)
TOGETHER = re.compile(r"\b(?:together|consolidat\w*|one\s+consignment|single\s+consignment|one\s+shipment|"
                      r"(?:one|single|same)\s+(?:AWB|air\s*waybill|MAWB|HAWB)|zusammen|gemeinsam|eine\s+sendung|"
                      r"einer\s+sendung|ensemble|juntos|insieme)\b", re.I)
READY = re.compile(r"\b(?:ready|available|bereit|abholbereit|verfügbar|versandbereit|prêt\w*|listo|lista|pronto)\b"
                   r"(?:\s+\w+){0,2}?\s+(?:on\s+|am\s+|from\s+|ab\s+|by\s+|le\s+|el\s+|il\s+)?"
                   r"(\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]?(?:\d{2,4})?)", re.I)


def _destinations(text: str) -> list[str]:
    """Destination airports named in the text (codes, or city names we price), not after "via"."""
    lanes = known()
    found = []
    for m in re.finditer(r"\b([A-Z]{3})\b", text):
        if m[1] in lanes and m[1] not in ORIGINS and not VIA.search(text[:m.start()]):
            found.append(m[1])
    plain = text.lower()
    for city, code in CITY.items():
        if code in lanes and code not in ORIGINS:
            for m in re.finditer(rf"(?<!\w){re.escape(city)}(?!\w)", plain):
                if not VIA.search(plain[:m.start()]):
                    found.append(code)
    return found


def several_shipments(mail: dict) -> str | None:
    """Why this RFQ holds more than one shipment, or None."""
    text = _request(mail)
    segments = [s for s in re.split(r"(?<=[.!?;])\s+|\n+", text) if WEIGHT.search(s)]
    weights = {w.group(0) for s in segments for w in WEIGHT.finditer(s)}
    places = list(dict.fromkeys(code for s in segments for code in _destinations(s)))
    if len(places) >= 2 and len(weights) >= 2:
        return f"{len(places)} destinations ({', '.join(places)})"
    if TOGETHER.search(text):
        return None
    if m := SEPARATE.search(text):
        return f"separate shipments (\"{m.group(0).strip()}\")"
    if dates := _lot_dates(text):
        return f"{len(dates)} ready dates ({', '.join(dates)})"
    return None


def _lot_dates(text: str) -> list[str]:
    """Two ready dates that each go with their own weight ("400 kg, ready 24.11. / 650 kg, ready 02.12."), never
    "available from 24.11., ready 25.11.: 140 kg each, 420 kg in total" (one lot)."""
    seen, dates = set(), []
    for d in READY.finditer(text):  # the first mention of each date, in order
        if (key := d[1].rstrip(".")) not in seen:
            seen.add(key)
            dates.append(d)
    if len(dates) < 2:
        return []
    first, second = dates[0], dates[1]
    weights = [w.start() for w in WEIGHT.finditer(text)]
    between = any(first.end() <= w < second.start() for w in weights)
    outside = any(w < first.start() or w >= second.end() for w in weights)
    return [d[1].rstrip(".") for d in dates] if between and outside else []


# ---- EXW / FCA at the customer's site ------------------------------------------------------------------------------

INCOTERM = re.compile(r"\b(?:EXW|ex[- ]works|ab\s+werk|FCA)\b", re.I)
AT_AIRPORT = re.compile(r"\b(?:airport|flughafen|aéroport|aeropuerto|aeroporto|terminal|airside|cargo\s+(?:center|centre|"
                        r"city|hub)|hub)\b|\b(?:CGN|DUS|FRA|HAM|MUC|STR)\b", re.I)
POSTCODE = re.compile(r"(?<![\d.,-])(\d{5})(?![\d.,])")
EXW = re.compile(r"\b(?:EXW|ex[- ]works|ab\s+werk)\b", re.I)  # always the seller's site; FCA only when it says so
PREMISES = re.compile(r"\b(?:our|unser\w*|the\s+shipper'?s|the\s+seller'?s|shipper'?s|seller'?s)\s+(?:plant|warehouse|"
                      r"site|factory|premises|works|werk|lager|standort|halle)\b", re.I)


def _sentences(paragraph: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?;])\s+(?=[A-ZÄÖÜ])|\n+", paragraph) if s.strip()]


def incoterm_pickup(mail: dict) -> dict | None:
    """{address, zone} when the terms put the goods at the customer's German site (EXW, or FCA there), else None."""
    for paragraph in re.split(r"\n\s*\n", _request(mail)):
        if not INCOTERM.search(paragraph):
            continue
        sentences = _sentences(paragraph)
        term = next((s for s in sentences if INCOTERM.search(s)), "")
        if AT_AIRPORT.search(term):
            continue  # "FCA Frankfurt Airport": the customer brings it to the airport
        for sentence in [term] + [s for s in sentences if s is not term]:
            for m in POSTCODE.finditer(sentence):
                if zone_airport({"address": m.group(1), "zone": None}):
                    return {"address": _address_line(sentence, m), "zone": None}
        if (EXW.search(term) or PREMISES.search(term)) and (town := _town(term)):  # "FCA Frankfurt": the airport
            return {"address": town[0], "zone": town[1]}
    return None


def _address_line(sentence: str, m: re.Match) -> str:
    """'Industriestr. 12, 85748 Garching' out of 'Terms are EXW our plant, Industriestr. 12, 85748 Garching.'"""
    head = sentence[:m.start()]
    cuts = [i + len(w) for w in (":", "EXW", "FCA", "ex works", "Ex Works", "ab Werk") if (i := head.rfind(w)) >= 0]
    line = sentence[max(cuts, default=0):].strip(" ,.;()")
    line = re.sub(r"^(?:our|unser\w*|the)\s+(?:plant|warehouse|site|factory|premises|werk|lager)\s*,?\s*", "", line,
                  flags=re.I)
    return line[:160] or sentence.strip()[:160]


def _town(text: str) -> tuple[str, str] | None:
    """(town, zone) of a pickup-zone town named in the text ("ab Werk (EXW) Ingolstadt" → ("Ingolstadt", "85"))."""
    if not (zone := city_zone(text)):
        return None
    plain = _plain(text)
    names = [area for area, z in AREAS.items() if z == zone and re.search(rf"\b{re.escape(area)}\b", plain)]
    return (max(names, key=len).title() if names else zone, zone)


def before_pricing(rfq: dict, mail: dict, missing: list[str]) -> tuple[list[str], list[str]]:
    """Applies the pre-pricing shape rules to rfq (in place). Returns (missing, notes for the session events)."""
    notes = []
    if INCOTERM_PICKUP and rfq.get("pickup") is None and (pickup := incoterm_pickup(mail)):
        origin = zone_airport(pickup)
        if origin:
            rfq["pickup"], rfq["origin"] = pickup, origin
            missing = [m for m in missing if m != "origin"]
            notes.append(f"EXW/FCA at the customer's site: door-to-port from {pickup['address']} via {origin}")
    if MULTI_SHIPMENT and (why := several_shipments(mail)):
        missing = [*missing, f"one quote per shipment ({why})"]
        notes.append(f"Several shipments in one RFQ: {why}. No combined price: a person answers")
    return missing, notes


# ---- quote gate sentences ------------------------------------------------------------------------------------------

DOOR_TERMS = re.compile(r"\b(?:DDP|DAP|DPU)\b")
DOOR_WORDS = re.compile(
    r"\bdoor[- ]to[- ]door\b|\bhaus[- ]zu[- ]haus\b|\btür[- ]zu[- ]tür\b|\bfrei\s+haus\b"
    r"|\b(?:deliver(?:y|ed|ing)?|on-?carriage|zustell\w*|lieferung|anlieferung)\b[^.\n]{0,40}?"
    r"\b(?:to|at|an|bei|beim|zum|zur|bis)\s+(?:the\s+|our\s+|their\s+|den\s+|dem\s+|die\s+|unsere[nm]?\s+)?"
    r"(?:end\s*)?(?:customer'?s?|consignee'?s?|client'?s?|receiver'?s?|recipient'?s?|door|empfänger\w*|kunden\w*|"
    r"endkunden\w*)(?!\w)"
    r"|\b(?:consignee|receiver|recipient|empfänger)'?s?\s+(?:address|door|warehouse|premises|site|adresse|lager)\b"
    r"|\bincl(?:uding|\.)?\s+(?:customs\s+clearance|import\s+clearance|duties|delivery\s+to)\b"
    r"|\binkl(?:usive|\.)?\s+(?:zustellung|verzollung|einfuhr\w*)\b", re.I)
DOOR_SENTENCE = (
    "Please note that the all-in price covers the air freight to {dest} airport: delivery to the consignee's door, "
    "import customs clearance and duties at destination are not included, and I'm happy to arrange them separately.",
    "Bitte beachten Sie: Der All-in-Preis gilt für die Luftfracht bis zum Flughafen {dest}. Die Zustellung an den "
    "Empfänger sowie Verzollung und Einfuhrabgaben am Zielort sind nicht enthalten, diese organisiere ich gern separat.")
SPEED = re.compile(r"\b(?:quick(?:ly|est)?|fast(?:er|est)?|speed|soon|swift|rapid(?:ly)?|express|schnell\w*|zügig|rasch|"
                   r"rápid\w*|rapide\w*|veloce|presto)\b", re.I)
PRICE = re.compile(r"\b(?:(?:best|good|low(?:est)?|competitive|sharp)\s+(?:price|rate|offer|quote)|price\s+matters|"
                   r"cost(?:s)?\s+matter|on\s+price|cheap\w*|economical|budget|preis\w*|günstig\w*|billig\w*|"
                   r"kosten\w*|prix|precio|prezzo)\b", re.I)
REPLY_SPEED = re.compile(r"\b(?:reply|respond|answer|get\s+back|quote|send|revert)\w*\b[^.!?\n]{0,25}?"
                         r"\b(?:quick(?:ly)?|fast|soon|promptly|asap)\b", re.I)
OTHER_SENTENCE = {
    "faster": ("If speed matters more, {carrier} gets it there sooner; just let me know and I'll quote that option "
               "instead.",
               "Falls Ihnen die Laufzeit wichtiger ist: {carrier} ist schneller, sagen Sie einfach Bescheid, dann biete "
               "ich Ihnen diese Option an."),
    "cheaper": ("If price matters more, {carrier} is the more economical option; just let me know and I'll quote that "
                "one instead.",
                "Falls Ihnen der Preis wichtiger ist: {carrier} ist günstiger, sagen Sie einfach Bescheid, dann biete "
                "ich Ihnen diese Option an."),
}


def _both_asks(request: str) -> bool:
    text = REPLY_SPEED.sub(" ", NOT_ASK.sub(" ", NOT_FAST.sub(" ", request)))
    return bool((CHEAP_WORDS.search(text) or PRICE.search(text)) and (FAST_WORDS.search(text) or SPEED.search(text)))


def _other_option(options: list[dict], chosen: dict, ask: str | None, cap: float | None) -> tuple[str, dict] | None:
    pool = [o for o in options if o.get("total") is not None and (cap is None or o["total"] <= cap)]
    if ask == "fastest":
        cheaper = [o for o in pool if o["total"] < chosen["total"] and o.get("carrier") != chosen.get("carrier")]
        return ("cheaper", min(cheaper, key=lambda o: o["total"])) if cheaper else None
    days = chosen.get("transit_days")
    faster = [o for o in pool if o.get("transit_days") is not None and days is not None and o["transit_days"] < days
              and o.get("carrier") != chosen.get("carrier")]
    return ("faster", min(faster, key=lambda o: (o["transit_days"], o["total"]))) if faster else None


def gate_sentences(rfq: dict, mail: dict, texts, options: list[dict], chosen: dict, lang: str,
                   cap: float | None = None) -> list[tuple[dict, str]]:
    """(finding, sentence) pairs for the quote gate. Sentences never contain digits (one amount per mail).
    texts: readable attachment texts (an SLI may name the Incoterm)."""
    out = []
    de = lang == "de"
    request = f"{mail.get('subject') or ''}\n{_request(mail)}"
    terms = "\n".join([request, *[t for t in texts or () if t]])
    if DESTINATION_DELIVERY and (m := DOOR_TERMS.search(terms) or DOOR_WORDS.search(request)):
        dest = rfq.get("destination") or ""
        if not re.search(r"\d", dest):
            out.append(({"code": "destination_delivery", "level": "fix",
                         "text": f"Delivery at destination asked ({m.group(0).strip()}): the quote says it is not included"},
                        DOOR_SENTENCE[de].format(dest=dest)))
    if BOTH_ASKS and _both_asks(request) and (other := _other_option(options, chosen, rfq.get("ask"), cap)):
        kind, option = other
        if not re.search(r"\d", option.get("carrier") or "0"):
            out.append(({"code": "both_asks", "level": "fix",
                         "text": f"Cheapest and fastest asked: {option['carrier']} named as the {kind} option (no amount)"},
                        OTHER_SENTENCE[kind][de].format(carrier=option["carrier"])))
    return out
