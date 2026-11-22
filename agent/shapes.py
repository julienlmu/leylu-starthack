"""RFQ shapes a single all-in quote must react to (rules on the mail text, no LLM call).

Before pricing (rfq_agent.handle_rfq, `before_pricing`):
- MULTI_SHIPMENT: two shipments in one RFQ (two destinations, or consignments that fly apart: "two separate
  consignments", two ready dates). One combined price is wrong either way. Sentences about other orders ("last week
  you moved 800 kg to ORD", "a second order may follow next month") are no shipment of this RFQ and are not counted.
  - quote (default, any value but off/hold): when lot 1 can be read from the mail text alone (its destination, its
    weight, its pieces, volume and dimensions only from its own lines), the rfq becomes lot 1, the quote states its
    one amount and one sentence says the other shipments get their own quote. When lot 1 can't be isolated, the
    extraction is quoted as read (main's behaviour) and the session says so. Never no quote.
  - hold: a person answers: added to `missing`, which hands the RFQ over without a quote (no fallback quote either).
  - off: not looked at (main's behaviour).
- INCOTERM_PICKUP: EXW / ex works / ab Werk, or FCA at the customer's site, with a German postcode or a pickup-zone town
  next to it: door-to-port (a trucker to the zone's airport), never airport-to-airport (round 1's too_low). FCA with
  only a town ("FCA Frankfurt") is the handover at that airport and stays airport-to-airport.

In the quote gate (gate.review section 7, `gate_sentences`), one sentence without digits each:
- MULTI_SHIPMENT=quote with lot 1 isolated: the quote is for the shipment to {dest1}; the others get their own quote.
- DESTINATION_DELIVERY: DDP / DAP / door-to-door / delivery to the consignee: we price to the destination airport, so
  the quote says that delivery, customs and duties at destination are not included (never silently port-to-port).
- BOTH_ASKS: "cheapest and fastest": the quote follows the ask the backend and the gate picked and names the option
  that wins the other ask in words, never with a second amount.
Each `<FLAG>=off` (env + restart) restores the behaviour before.
"""

import os
import re
from datetime import date

import gate_lang
import units
from airports import CITY, known
from extract import (AREAS, CHEAP_WORDS, FAST_WORDS, NOT_ASK, NOT_FAST, SIGN_OFF, TO_CM, TO_KG, TO_M3, _plain,
                     city_zone, doubts, zone_airport)
from inbox import latest_text


def multi_mode(value: str | None) -> str:
    """MULTI_SHIPMENT: "off" (main's behaviour), "hold" (a person, no quote), anything else "quote" (lot 1 only)."""
    value = (value or "quote").strip().lower()
    return value if value in ("off", "hold") else "quote"


MULTI_SHIPMENT = multi_mode(os.environ.get("MULTI_SHIPMENT"))
INCOTERM_PICKUP = os.environ.get("INCOTERM_PICKUP", "on").lower() != "off"
DESTINATION_DELIVERY = os.environ.get("DESTINATION_DELIVERY", "on").lower() != "off"
BOTH_ASKS = os.environ.get("BOTH_ASKS", "on").lower() != "off"

ORIGINS = {"CGN", "DUS", "FRA", "HAM", "MUC", "STR"}


def _request(mail: dict) -> str:
    """The customer's own words: the newest mail, without the signature (a company address is no pickup)."""
    return SIGN_OFF.split(latest_text(mail.get("body") or ""), 1)[0]


# ---- several shipments ---------------------------------------------------------------------------------------------

WEIGHT = re.compile(r"\d[\d.,]*\s*(?:kgs?|kilograms?|kilos?|lbs?|pounds?|t|tonnes?|tons?)\b", re.I)
_PARTICIPLE = r"(?:sent|moved|shipped|flown|delivered|booked|handled|arrived|transported|carried|forwarded)"
_PARTIZIP = r"(?:geschickt|verschickt|versandt|versendet|geliefert|transportiert|geflogen|gebucht|abgewickelt)"
# A sentence about another order, earlier or later, is no shipment of this RFQ ("Last week you moved 800 kg to ORD",
# "Our previous shipment to Dubai (1,2 t) arrived late", "a second order of 200 kg to BKK may follow next month").
# "before" / "already" / "later" only with a past verb or an order word: "ready before 24.11." and "no later than"
# are this shipment.
OTHER_ORDER = re.compile(
    r"\b(?:last|previous|prior|earlier|former)\s+(?:week|month|year|quarter|time|shipments?|orders?|consignments?|"
    r"deliver(?:y|ies)|bookings?|lots?|loads?|moves?)\b|\bpreviously\b|\bin\s+the\s+past\b|\bas\s+before\b"
    r"|\b(?:a|one|two|three|few|several|\d+)\s+(?:days?|weeks?|months?|years?)\s+ago\b"
    r"|\b(?:shipments?|orders?|consignments?|time)\s+before\b"
    rf"|\b(?:we|you|they|it|he|she|i)\s+(?:\w+\s+)?(?:sent|moved|shipped|flew|delivered|booked|handled|arrived|"
    rf"transported|forwarded|carried)\b"
    rf"|\b(?:was|were|has\s+been|have\s+been|had\s+been|have|has|had)\s+(?:already\s+|just\s+)?{_PARTICIPLE}\b"
    rf"|\balready\s+(?:{_PARTICIPLE}|went|left)\b|\barrived\b|\bflew\b"
    r"|\b(?:may|might|will|could|would|should|to)\s+(?:\w+\s+)?follow\b|\bfollows?\s+(?:later|next|soon|shortly)\b"
    r"|\bnext\s+(?:week|month|year|quarter|time)\b|(?<!\bno\s)(?<!\bnot\s)\blater\b|\bin\s+(?:the\s+)?future\b"
    r"|\bfuture\s+(?:orders?|shipments?|consignments?|inquiries|enquiries|requests?|business)\b"
    r"|\b(?:letzte[nrms]?|vergangene[nrms]?|vorige[nrms]?)\s+(?:woche|monat|jahr|quartal|mal|sendung|lieferung|"
    r"auftrag|bestellung)\b|\bvorherige\w*|\bfrühere\w*|\bzuletzt\b|\bangekommen\b"
    rf"|\b(?:bereits|schon)\s+(?:\w+\s+){{0,4}}?{_PARTIZIP}\b(?!\s+(?:werden|wird))"
    rf"|\b(?:haben|hat|hatten|hatte|ist|sind|war|waren|wurde|wurden)\b[^.!?\n]{{0,60}}?\b{_PARTIZIP}\b"
    r"(?!\s+(?:werden|wird))"
    r"|\bnächste[nrms]?\s+(?:woche|monat|jahr|quartal|mal)\b|\bfolgt\s+(?:eventuell|evtl\.?|vielleicht|später|noch)\b"
    r"|\b(?:eventuell|evtl\.|vielleicht)\s+(?:\w+\s+){0,3}?folg\w*|(?<!\bnicht\s)\bspäter\b|\bin\s+zukunft\b"
    r"|\b(?:zu)?künftig\w*", re.I)


def _current(text: str) -> str:
    """The request without the sentences about other orders, one sentence per line."""
    return "\n".join(s for s in re.split(r"(?<=[.!?;])\s+|\n+", text) if s.strip() and not OTHER_ORDER.search(s))
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
                      r"(?:one|single|combined)\s+(?:all[- ]in\s+)?(?:price|quote|offer|rate)(?!\s+(?:per|for\s+each|each))|"
                      r"(?:total|price|quote)\s+for\s+(?:both|all)\b(?![^.\n]{0,20}separately)|"
                      r"(?:one|single|same)\s+(?:AWB|air\s*waybill|MAWB|HAWB)|zusammen|gemeinsam|eine\s+sendung|"
                      r"einer\s+sendung|ensemble|juntos|insieme)\b", re.I)
# "one total for both" / "a combined price": with two lanes, lot 1's amount would read as the price for both
ONE_TOTAL = re.compile(r"\b(?:(?:total|price|quote|offer|rate)\s+for\s+(?:both|all)\b|(?:one|single|combined|overall)\s+"
                       r"(?:all[- ]in\s+)?(?:total|price|quote|offer|rate)\b(?!\s+(?:per|for\s+each|each))|"
                       r"(?:gesamtpreis|gesamtangebot|ein\s+preis)\s+für\s+(?:beide|alle))", re.I)
# R89/R90: "a separate all-in price in EUR for each shipment rather than a combined total" asks for the OPPOSITE
SEPARATE = re.compile(r"\b(?:rather\s+than|instead\s+of|not|no|never|statt|anstatt|kein\w*|plut[ôo]t\s+qu|en\s+lugar\s+de|"
                      r"invece\s+di)\s+(?:\w+\s+){0,2}$|\bseparate\s+(?:all[- ]in\s+)?(?:price|quote|offer)s?\b|"
                      r"\b(?:price|quote|offer)\s+for\s+each\b|\bfor\s+each\s+(?:shipment|lot|destination)\b|"
                      r"\bje\s+sendung\b|\bgetrennt\w*\s+preis", re.I)


def _one_total(text: str) -> bool:
    """A real "one total for both" ask: not negated ("rather than a combined total") and no "separate price for each"."""
    for m in ONE_TOTAL.finditer(text):
        if SEPARATE.search(text[max(0, m.start() - 30):m.start()]):
            continue  # "rather than a combined total": negated
        sentence = re.split(r"(?<=[.!?\n])", text[:m.start()])[-1] + text[m.start():].split(".")[0]
        if re.search(r"\bseparate\b|\bfor\s+each\b|\beach\s+shipment\b", sentence, re.I):
            continue  # same sentence asks for a price per shipment
        return True
    return False


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
    text = _current(_request(mail))
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


# ---- lot 1 of several shipments (MULTI_SHIPMENT=quote) -------------------------------------------------------------

LOT_MARK = re.compile(  # where a lot starts inside a sentence: "Lot B:", "Sendung 2:", "second shipment", "2) "
    r"(?=\b(?i:lot|shipment|consignment|sendung|partie|order|auftrag)\s*(?:[A-H]|\d{1,2}|(?i:one|two|three|eins|zwei|"
    r"drei))(?!\w))"
    r"|(?=\b(?i:first|second|third|erste[nrs]?|zweite[nrs]?|dritte[nrs]?)\s+(?i:shipment|lot|consignment|sendung|"
    r"partie|lieferung)\b)"
    r"|(?=(?<![^\s(])(?:\d|[a-c])\)\s)")
CONJ = re.compile(r"\s*,?\s+(?:and|und|plus|sowie|as\s+well\s+as|&)\s+", re.I)
NOUNS = (r"(?:pallets?|plts?|crates?|boxes|box|cartons?|ctns?|cases?|pieces?|pcs|pc|pkgs?|packages?|colli|drums?|skids?|"
         r"units?|bundles?|rolls?|bags?|totes?|coils?|machines?|kisten?|europaletten?|paletten?|kartons?|packstücke?|"
         r"stücke?|stk|fässer|fass|gitterbox(?:en)?|maschinen?)")
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "single": 1, "ein": 1, "eine": 1, "einen": 1, "two": 2, "zwei": 2,
                "three": 3, "drei": 3, "four": 4, "vier": 4, "five": 5, "fünf": 5, "six": 6, "sechs": 6, "seven": 7,
                "sieben": 7, "eight": 8, "acht": 8, "nine": 9, "neun": 9, "ten": 10, "zehn": 10}
COUNT = re.compile(rf"(?<![\d.,])(\d{{1,4}})\s*(?:x\s*)?{NOUNS}\b"
                   rf"|\b({'|'.join(NUMBER_WORDS)})\s+(?:[a-zäöü-]+\s+)?{NOUNS}\b"
                   r"|(?<![\d.,])(\d{1,3})\s*[x×]\s*(?=\d+(?:[.,]\d+)?\s*(?:cm|mm|in|m)?\s*[x×*])", re.I)
VOLUME = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)*)\s*(?:(cbm\b|m3\b|m³|m\^3|cubic\s+met(?:er|re)s?\b|kubikmeter\b)|"
                    r"(cu\.?\s?ft\b|cft\b|ft3\b|ft³|cubic\s+f(?:ee|oo)t\b)|(lit(?:er|re)s?\b|ltrs?\b))", re.I)
ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})|(\d{1,2})[./](\d{1,2})[./]?(\d{4}|\d{2})?")


class NotIsolated(ValueError):
    pass


def _units(text: str) -> list[str]:
    """The request cut into lot-sized parts: lines and sentences, then at lot marks, then at "and" between two parts
    that each have a weight."""
    out = []
    for segment in re.split(r"(?<=[.!?;])\s+|\n+", text):
        for part in LOT_MARK.split(segment):
            pieces = CONJ.split(part)
            current = pieces[0]
            for following in pieces[1:]:
                if WEIGHT.search(current) and WEIGHT.search(following):
                    out.append(current)
                    current = following
                else:
                    current = f"{current} and {following}"
            out.append(current)
    return [u.strip(" ,;:") for u in out if u.strip(" ,;:")]


def _one(values: set[float], known: list[float]) -> float:
    """The one reading of a number ("1,100" is 1100 or 1.1: the one the extraction also has), else NotIsolated."""
    if len(values) == 1:
        return next(iter(values))
    agree = {v for v in values if any(abs(v - k) <= 0.005 * max(v, k) for k in known)}
    if len(agree) == 1:
        return agree.pop()
    raise NotIsolated(f"the number reads {sorted(values)}")


def _window(text: str, m: re.Match) -> tuple[str, str]:
    """(text before, text after) the match, each up to the next number."""
    before, after = text[max(0, m.start() - 45):m.start()], text[m.end():m.end() + 40]
    last = max((i for i, c in enumerate(before) if c in units.DIGITS), default=-1)
    first = next((i for i, c in enumerate(after) if c in units.DIGITS), len(after))
    return before[last + 1:], after[:first]


def _lot_piece(lot: str, lines: list[dict]) -> tuple[dict, float | None]:
    """(piece, volume m3 or None) of one lot, from its own text only. lines: the extraction's piece lines, used only
    to settle a reading the text leaves open (which split of "1,100", each or total, dimensions without a unit)."""
    weights = list(WEIGHT.finditer(lot))
    if len(weights) != 1:
        raise NotIsolated(f"{len(weights)} weights in lot 1")
    w = weights[0]
    token = re.match(r"\d[\d.,]*", w.group(0)).group(0)
    word = w.group(0)[len(token):].strip().lower()
    to_kg = TO_KG["lb" if word.startswith(("lb", "pound")) else "kg" if word.startswith("k") else "t"]
    line_kg = [p["count"] * p["weight_kg"] for p in lines if p.get("weight_kg")] + \
              [p["weight_kg"] for p in lines if p.get("weight_kg")]
    kg = _one({v * to_kg for v in units.readings(token)}, line_kg)

    counts = []
    for m in COUNT.finditer(lot):
        counts.append(int(m[1] or m[3]) if (m[1] or m[3]) else NUMBER_WORDS[m[2].lower()])
    before, after = _window(lot, w)
    each = bool(units.EACH_AFTER.search(after) or units.EACH_BEFORE.search(before))
    total = bool(units.TOTAL_AFTER.search(after) or units.TOTAL_BEFORE.search(before))
    if each and total or (each and len(counts) > 1):
        raise NotIsolated("each and total, or each over several piece kinds")
    count = sum(counts) if counts else None
    match = [p for p in lines if p.get("weight_kg") and (count is None or p["count"] == count)
             and (abs(p["count"] * p["weight_kg"] - kg) <= 0.005 * kg or abs(p["weight_kg"] - kg) <= 0.005 * kg)]
    if count is None:
        count = match[0]["count"] if len(match) == 1 else 1
    if not each and not total and count > 1 and len(match) == 1:  # the mail doesn't say: as the extraction read it
        each = abs(match[0]["count"] * match[0]["weight_kg"] - kg) > 0.005 * kg  # its line is kg per piece
    per_kg = kg if each or count == 1 else kg / count  # no word and no line: the lot's weight is its total

    dims = [None, None, None]
    triples = list(units.TRIPLE.finditer(lot))
    if len(triples) > 1 or (triples and len(counts) > 1):
        raise NotIsolated("dimensions for several piece kinds")
    if triples:
        t = triples[0]
        unit = next((u.lower() for u in (t[2], t[4], t[6]) if u), None)
        if unit:
            unit = "in" if unit.startswith("in") or unit in ('"', "”", "″") else unit
            dims = [round(_one(units.readings(t[i]), []) * TO_CM[unit], 1) for i in (1, 3, 5)]
        elif len(match) == 1 and match[0].get("length_cm"):
            dims = [match[0]["length_cm"], match[0]["width_cm"], match[0]["height_cm"]]
        else:
            raise NotIsolated("dimensions without a unit")
    elif len(match) == 1 and match[0].get("length_cm") and match[0].get("width_cm") and match[0].get("height_cm"):
        dims = [match[0]["length_cm"], match[0]["width_cm"], match[0]["height_cm"]]

    volume = None
    volumes = list(VOLUME.finditer(lot))
    if len(volumes) > 1:
        raise NotIsolated("several volumes")
    if volumes:
        v = volumes[0]
        volume = _one(units.readings(v[1]), []) * TO_M3["m3" if v[2] else "ft3" if v[3] else "l"]
        if units.EACH_AFTER.search(_window(lot, v)[1]):
            volume *= count
    piece = {"count": count, "length_cm": dims[0], "width_cm": dims[1], "height_cm": dims[2],
             "weight_kg": round(per_kg, 6)}
    return piece, (round(volume, 4) if volume else None)


def _origins(text: str) -> list[str]:
    found = [m[1] for m in re.finditer(r"\b([A-Z]{3})\b", text) if m[1] in ORIGINS]
    plain = text.lower()
    found += [code for city, code in CITY.items() if code in ORIGINS and re.search(rf"(?<!\w){re.escape(city)}(?!\w)", plain)]
    return list(dict.fromkeys(found))


def _ready(text: str, fallback: str | None) -> str | None:
    if not (m := READY.search(text)) or not (d := ISO.search(m[1])):
        return fallback
    try:
        if d[1]:
            y, mo, day = int(d[1]), int(d[2]), int(d[3])
        else:
            year = d[6] or (fallback or "2026")[:4]
            y, mo, day = int(year) + (2000 if len(year) == 2 else 0), int(d[5]), int(d[4])
        return date(y, mo, day).isoformat()
    except ValueError:
        return fallback


def first_lot(mail: dict, rfq: dict, why: str) -> dict | None:
    """{"rfq": the request for lot 1 only, "destination", "others", "summary"}, or None when the mail text doesn't
    give lot 1 on its own (then the extraction is quoted as read)."""
    try:
        lots = [u for u in _units(_current(_request(mail))) if WEIGHT.search(u)]
        if len(lots) < 2:
            raise NotIsolated("fewer than two lots with a weight")
        places = [list(dict.fromkeys(_destinations(u))) for u in lots]
        if any(len(p) > 1 for p in places):
            raise NotIsolated("a lot names two destinations")
        if "destinations" in why.split("(")[0] and not all(places):
            raise NotIsolated("a lot without its destination")
        if any(places) and not all(places):
            raise NotIsolated("some lots name a destination, some don't")
        lot = lots[0]
        destination = places[0][0] if places[0] else rfq.get("destination")
        if not destination:
            raise NotIsolated("no destination for lot 1")
        piece, volume = _lot_piece(lot, rfq.get("pieces") or [])
        new = {**rfq, "destination": destination, "pieces": [piece], "volume_m3": volume,
               "ready_date": _ready(lot, rfq.get("ready_date"))}
        if (origins := _origins(lot)) and rfq.get("pickup") is None:
            if len(origins) > 1:
                raise NotIsolated("lot 1 names two origins")
            new["origin"] = origins[0]
        others = list(dict.fromkeys(d for p in places[1:] for d in p if d != destination))
        new["shipment_lot"] = {"lot": 1, "of": len(lots), "destination": destination, "others": others}
    except (NotIsolated, ValueError, KeyError, TypeError, ZeroDivisionError) as error:
        print(f"lot 1 not isolated: {type(error).__name__}: {error}")
        return None
    kg = piece["count"] * piece["weight_kg"]
    summary = f"{piece['count']} pcs, {kg:g} kg" + (f", {volume:g} m3" if volume else "") + f" to {destination}"
    return {"rfq": new, "destination": destination, "others": others, "summary": summary}


def _still_missing(rfq: dict, missing: list[str]) -> list[str]:
    """`missing` for the lot-1 request: what lot 1 answers drops out, the density is checked again."""
    pieces = rfq.get("pieces") or []
    dims = pieces and all(p.get("length_cm") and p.get("width_cm") and p.get("height_cm") for p in pieces)
    kept = []
    for m in missing:
        if m in ("origin", "destination") and rfq.get(m):
            continue
        if m == "weight" and pieces and all(p.get("weight_kg") for p in pieces):
            continue
        if m == "dimensions or volume" and (dims or rfq.get("volume_m3")):
            continue
        if m.startswith("implausible density") or m.startswith("one piece line is the total"):
            continue
        kept.append(m)
    return kept + [d for d in doubts(rfq) if d.startswith("implausible density")]


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
    import gate  # here: gate imports shapes
    if gate._self_delivery(_request(mail)):
        return None  # "EXW Kelsterbach. We deliver the goods to FRA airport ourselves.": no trucker (too_high)
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
    if MULTI_SHIPMENT != "off" and (why := several_shipments(mail)):
        one_total = "destinations" in why.split("(")[0] and _one_total(_current(_request(mail)))
        if MULTI_SHIPMENT == "hold" or one_total:  # "one total for both" lanes: lot 1's price would read as both
            missing = [*missing, f"one quote per shipment ({why})"]
            notes.append(f"Several shipments in one RFQ: {why}. No combined price: a person answers")
        elif lot := first_lot(mail, rfq, why):
            rfq.clear()
            rfq.update(lot["rfq"])  # in place: handle_rfq keeps its reference
            missing = _still_missing(rfq, missing)
            others = f" (the shipment to {', '.join(lot['others'])} gets no price here)" if lot["others"] else ""
            notes.append(f"Several shipments in one RFQ: {why}. The quote covers lot 1 only: {lot['summary']}{others}")
        else:
            notes.append(f"Several shipments in one RFQ: {why}. Lot 1 can't be read on its own from the mail: "
                         f"quoted as read")
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
DOOR_MUST = re.compile(r"\b(?:mandatory|required|a\s+must|must\s+(?:be|include)|essential|obligatory|non[- ]negotiable|"
                       r"needs?\s+to\s+(?:be|include)|has\s+to\s+(?:be|include)|zwingend|verpflichtend|erforderlich|"
                       r"(?:ist|sind)\s+(?:pflicht|ein\s+muss)|muss|müssen)\b", re.I)
DOOR_ASK = (
    "Thanks for your request. Our price covers the air freight to {dest} airport; delivery to the consignee's door, "
    "import customs clearance and duties at destination I arrange with a local partner. Shall I get those quoted too, "
    "or is an airport-to-airport price fine for you?",
    "Danke für Ihre Anfrage. Unser Preis gilt für die Luftfracht bis zum Flughafen {dest}; die Zustellung an den "
    "Empfänger, die Verzollung und die Einfuhrabgaben organisiere ich mit einem Partner vor Ort. Soll ich diese "
    "ebenfalls anbieten lassen, oder passt Ihnen ein Preis bis zum Flughafen?")
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


LOT_SENTENCE = {  # (en, de) by (other destinations named?, more than one other shipment?)
    (True, False): ("This quote is for the shipment to {dest}; for the shipment to {others} I'll send you a separate "
                    "quote, or just confirm its details.",
                    "Dieses Angebot gilt für die Sendung nach {dest}; für die Sendung nach {others} schicke ich Ihnen "
                    "ein separates Angebot, oder bestätigen Sie mir einfach kurz die Details."),
    (True, True): ("This quote is for the shipment to {dest}; for the shipments to {others} I'll send you separate "
                   "quotes, or just confirm their details.",
                   "Dieses Angebot gilt für die Sendung nach {dest}; für die Sendungen nach {others} schicke ich Ihnen "
                   "separate Angebote, oder bestätigen Sie mir einfach kurz die Details."),
    (False, False): ("This quote is for the first of your shipments; for the other one I'll send you a separate quote, "
                     "or just confirm its details.",
                     "Dieses Angebot gilt für die erste Ihrer Sendungen; für die weitere schicke ich Ihnen ein "
                     "separates Angebot, oder bestätigen Sie mir einfach kurz die Details."),
    (False, True): ("This quote is for the first of your shipments; for the others I'll send you separate quotes, or "
                    "just confirm their details.",
                    "Dieses Angebot gilt für die erste Ihrer Sendungen; für die weiteren schicke ich Ihnen separate "
                    "Angebote, oder bestätigen Sie mir einfach kurz die Details."),
}


def _lot_sentence(rfq: dict, lang: str) -> tuple[dict, str] | None:
    lot = rfq.get("shipment_lot")
    if MULTI_SHIPMENT != "quote" or not isinstance(lot, dict):
        return None
    dest, others = lot.get("destination") or "", list(lot.get("others") or [])
    if re.search(r"\d", dest + "".join(others)):
        return None
    several = (len(others) if others else (lot.get("of") or 2) - 1) > 1
    sentence = gate_lang.pick(LOT_SENTENCE[(bool(others), several)], lang).format(
        dest=dest, others=f" {gate_lang.AND.get(lang, 'and')} ".join(others))
    return ({"code": "first_lot", "level": "fix", "text": f"Several shipments: the quote is for lot 1 ({dest}) only"},
            sentence)


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
    if lot := _lot_sentence(rfq, lang):  # MULTI_SHIPMENT=quote: the quote is for lot 1 only
        out.append(lot)
    if DESTINATION_DELIVERY and (m := DOOR_TERMS.search(terms) or DOOR_WORDS.search(request)):
        dest = rfq.get("destination") or ""
        sentence = re.split(r"[.!?\n](?:\s|$)", terms[:m.start()])[-1] + re.split(r"[.!?\n](?:\s|$)", terms[m.start():])[0]
        if not re.search(r"\d", dest) and DOOR_MUST.search(sentence):
            # trap 20: the door leg or duties are a must, not a wish: ask before an airport-to-airport price
            out.append(({"code": "destination_delivery", "level": "hold",
                         "text": f"Delivery at destination is a must ({m.group(0).strip()}): asked the customer"},
                        gate_lang.pick(DOOR_ASK, lang).format(dest=dest)))
        elif not re.search(r"\d", dest):
            out.append(({"code": "destination_delivery", "level": "fix",
                         "text": f"Delivery at destination asked ({m.group(0).strip()}): the quote says it is not included"},
                        gate_lang.pick(DOOR_SENTENCE, lang).format(dest=dest)))
    if BOTH_ASKS and _both_asks(request) and (other := _other_option(options, chosen, rfq.get("ask"), cap)):
        kind, option = other
        if not re.search(r"\d", option.get("carrier") or "0"):
            out.append(({"code": "both_asks", "level": "fix",
                         "text": f"Cheapest and fastest asked: {option['carrier']} named as the {kind} option (no amount)"},
                        gate_lang.pick(OTHER_SENTENCE[kind], lang).format(carrier=option["carrier"])))
    return out


gate_lang.register({"door_sentence": DOOR_SENTENCE, "door_ask": DOOR_ASK, "faster": OTHER_SENTENCE["faster"],
                    "cheaper": OTHER_SENTENCE["cheaper"], "lot_one_named": LOT_SENTENCE[(True, False)],
                    "lot_several_named": LOT_SENTENCE[(True, True)], "lot_one": LOT_SENTENCE[(False, False)],
                    "lot_several": LOT_SENTENCE[(False, True)]})
