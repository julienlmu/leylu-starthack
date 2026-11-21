"""Quote mails that read like Lena wrote them (5U's per-round "humanity" bonus). QUOTE_STYLE=a or b, English + German.

a (code, $0): mirrors the customer's tone (Dear Ms X / Hello Tobias / Hi Klaus), answers their questions from our data
  (earliest departure and arrival, drop-off cut-off, one air waybill, space), replies to small talk once, names their
  goods and pickup town, and varies its sentences per request (seeded, deterministic).
b (one gpt-6-luna call): the model writes the body with {PRICE} from a facts JSON; code inserts the amount and checks
  it (one amount, only numbers from the facts, DG papers, how to accept). Any failure → a.

Hard rules for both: exactly one money amount (the all-in total, currency named); dates, times and airlines only from
the RFQ and the chosen option; DG → ask for the Shipper's Declaration for Dangerous Goods and the MSDS; signed Lena.
"""
import json
import re
import time
import zlib
from datetime import date

import gate
import llm
from inbox import latest_text
from quote_style import CITIES, _dates, safe_reference

SIGNER, TEAM = "Lena", "Leylü Air Freight"
FEMALE = {"anna", "sara", "sarah", "petra", "mira", "maria", "julia", "laura", "sophie", "sofia", "katharina", "sabine",
          "claudia", "nina", "lisa", "eva", "emma", "hannah", "marie", "susanne", "monika", "birgit", "karin", "ingrid",
          "christina", "stefanie", "nicole", "melanie", "lena", "elena", "jessica", "jennifer", "emily", "olivia",
          "charlotte", "johanna", "franziska", "carla", "clara", "lea", "leonie", "ursula", "heike", "anja", "silke"}
MALE = {"klaus", "tobias", "jonas", "thomas", "michael", "peter", "stefan", "andreas", "markus", "martin", "frank",
        "jan", "lukas", "felix", "paul", "david", "daniel", "christian", "florian", "matthias", "sebastian", "alexander",
        "max", "hans", "jürgen", "juergen", "uwe", "johannes", "simon", "philipp", "oliver", "benjamin", "james", "john",
        "robert", "william", "richard", "george", "henrik", "lars", "erik", "wolfgang", "dieter", "bernd", "ralf"}
WEEKDAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
             "Dezember"]
CITIES_DE = {"Munich": "München", "Cologne": "Köln", "Hanover": "Hannover", "Nuremberg": "Nürnberg", "Tokyo": "Tokio",
             "Cairo": "Kairo", "Mexico City": "Mexiko-Stadt", "Beijing": "Peking", "Seoul": "Seoul"}

FORMAL_HI = re.compile(r"^\s*(dear\b|sehr geehrte|to whom)", re.I)
CASUAL_HI = re.compile(r"^\s*(hi|hey|hallo|moin|servus)\b", re.I)
FORMAL_BYE = re.compile(r"kind regards|yours (sincerely|faithfully)|mit freundlichen gr|freundliche gr", re.I)
CASUAL_BYE = re.compile(r"\bcheers\b|\bthanks a lot\b|lovely day|\bliebe gr|\blg\b", re.I)
HOPE_WEEK = re.compile(r"\bhope (your|you|the|all)\b.{0,30}\b(week|day|well|good|great)|hoffe.{0,30}(woche|gut)", re.I)
NICE_DAY = re.compile(r"\b(have a (lovely|great|nice|good) (day|week|weekend)|happy friday|schönen (tag|abend))", re.I)
GREETINGS_FROM = re.compile(r"(?:greetings|grüße|gruesse) (?:from|aus) ([A-ZÄÖÜ][\wäöüß-]+(?: [A-ZÄÖÜ][\wäöüß-]+)?)")
SORRY = re.compile(r"\b(sorry|apologi[sz]e|entschuldig)\w*\b.{0,60}\b(left out|forgot|missed|vergessen)", re.I | re.S)
ASK_DEPART = re.compile(r"earliest (available )?departure|when (it|the shipment|the cargo) (could|would|can) (leave|depart)|"
                        r"frühest\w* (abflug|abfahrt)", re.I)
ASK_ARRIVE = re.compile(r"(earliest|expected) (available )?arrival|when (it|the shipment|the cargo|they) would arrive|"
                        r"when .{0,20}arrive|transit time|how long|frühest\w* ankunft|ankunft|laufzeit", re.I)
ASK_CUTOFF = re.compile(r"drop[- ]?off time|cut[- ]?off|latest (delivery|handover|drop)|anlieferzeit|annahmeschluss",
                        re.I)
ASK_SPACE = re.compile(r"confirm (the )?(space|availability|capacity)|verfügbarkeit", re.I)
ONE_AWB = re.compile(r"air ?waybill|single consignment|one consignment|both lots|all lots|eine sendung|luftfrachtbrief",
                     re.I)
POSTCODE_CITY = re.compile(r"\b(\d{5})\s*[(,]?\s*([A-ZÄÖÜ][\wäöüß.\-]*(?: [A-ZÄÖÜ][\wäöüß.\-]*)*)")


def _pick(options: list[str], seed: str, key: str) -> str:
    return options[zlib.crc32(f"{seed}|{key}".encode()) % len(options)]


def _lang(rfq: dict) -> str:
    return "de" if (rfq.get("language") or "en").lower()[:2] == "de" else "en"


def _day(d: date, lang: str) -> str:
    if lang == "de":
        return f"{WEEKDAYS_DE[d.weekday()]}, {d.day}. {MONTHS_DE[d.month - 1]}"
    return f"{d:%A} {d.day} {d:%B}"


def _city(code: str | None, lang: str) -> str:
    city = CITIES.get((code or "").upper())
    return (CITIES_DE.get(city, city) if lang == "de" else city) if city else (code or "")


def _place(code: str | None, lang: str) -> str:
    city = _city(code, lang)
    return f"{city} ({code})" if city != (code or "") else (code or "")


def pickup_town(rfq: dict) -> tuple[str | None, str | None]:
    """(postcode, town) from the pickup address: "61018 (Bad Homburg), Germany" → ("61018", "Bad Homburg")."""
    m = POSTCODE_CITY.search(((rfq.get("pickup") or {}).get("address") or ""))
    return (m.group(1), m.group(2).strip(" .,")) if m else (None, None)


def tone(body: str) -> str:
    """formal | neutral | casual, from the greeting first, then the closing."""
    first = next((line for line in body.splitlines() if line.strip()), "")
    if FORMAL_HI.search(first):
        return "formal"
    if CASUAL_HI.search(first):
        return "casual"
    if CASUAL_BYE.search(body) or body.count("!") >= 2:
        return "casual"
    return "formal" if FORMAL_BYE.search(body) else "neutral"


def _title(first: str, lang: str) -> str | None:
    key = first.lower()
    if key in FEMALE:
        return "Frau" if lang == "de" else "Ms"
    if key in MALE:
        return "Herr" if lang == "de" else "Mr"
    return None


def greeting(name: str | None, style: str, lang: str) -> str:
    parts = (name or "").split()
    first, last = (parts[0], parts[-1]) if parts else (None, None)
    title = _title(first, lang) if first else None
    if lang == "de":
        if style == "formal":
            if title and len(parts) > 1:
                return f"Sehr geehrte{'r' if title == 'Herr' else ''} {title} {last},"
            return f"Guten Tag {name}," if name else "Sehr geehrte Damen und Herren,"
        return f"Hallo {first}," if first else "Hallo,"
    if style == "formal":
        if title and len(parts) > 1:
            return f"Dear {title} {last},"
        return f"Dear {name}," if name else "Dear Sir or Madam,"
    if style == "casual":
        return f"Hi {first}," if first else "Hi there,"
    return f"Hello {first}," if first else "Hello,"


def _facts(rfq: dict, option: dict, today: date) -> dict:
    """Everything a mail may say, from our data only (dates computed in code)."""
    lang = _lang(rfq)
    start, departs, arrives = _dates(rfq, option, today)
    count = sum(int(p.get("count") or 0) for p in rfq.get("pieces") or []) or 1
    goods = (rfq.get("commodity") or "").strip()
    goods = goods if goods and len(goods) <= 60 and not re.search(r"\d", goods) else ""
    postcode, town = pickup_town(rfq)
    return {
        "language": lang, "pieces": count, "goods": goods, "ask": rfq.get("ask") or "cheapest",
        "carrier": option["carrier"], "door_pickup": bool(rfq.get("pickup")), "pickup_town": town,
        "pickup_postcode": postcode, "origin_airport": rfq.get("origin"), "origin_city": _city(rfq.get("origin"), lang),
        "destination_airport": rfq.get("destination"), "destination_city": _city(rfq.get("destination"), lang),
        "pickup_or_handover_date": _day(start, lang), "departure_date": _day(departs, lang),
        "arrival_date": _day(arrives, lang), "transit_days": max(1, (arrives - departs).days),
        "dangerous_goods": bool(rfq.get("dangerous_goods")), "reference": safe_reference(rfq),
        "currency": option["currency"], "_dates": (start, departs, arrives),
    }


def _amount(option: dict) -> str:
    return f"{option['currency']} {option['total']:,.2f}"


# ---- variant a: code only ------------------------------------------------------------------------------------------

EN = {
    "thanks": {"formal": ["Thank you for your enquiry{ref}.", "Thank you for your request{ref}."],
               "neutral": ["Thanks for your request{ref}.", "Thank you for getting in touch{ref}."],
               "casual": ["Thanks for sending this over{ref}.", "Thanks for the request{ref}."]},
    "week": ["Thanks, all good here, and I hope your week is going well too.",
             "All good on my side, thanks, and I hope yours is going well too."],
    "sorry": ["Thanks for sending the pickup location, that was all I needed.",
              "No problem at all, thanks for the pickup details."],
    "ask": {"cheapest": "the most economical option", "fastest": "the fastest option"},
    "offer": ["For your {goods}, {ask} is {carrier} from {o} to {d}.",
              "I've looked at the options for your {goods}, and {ask} is {carrier} from {o} to {d}.",
              "{Ask} for your {goods} is {carrier}, flying {o} to {d}."],
    "door": ["We'd collect {them} {at_town} on {start}, the flight leaves on {departs} and {they} should land in "
             "{dcity} around {arrives}.",
             "Our truck picks {them} up {at_town} on {start}, then {they} fly out on {departs} and should be in {dcity} "
             "around {arrives}."],
    "port": ["Once {they're} at {ocity} airport, the flight leaves on {departs} and {they} should land in {dcity} "
             "around {arrives}, so {n} in transit.",
             "{They} fly out of {ocity} on {departs} and should be in {dcity} around {arrives}, {n} in transit."],
    "earliest": ["As for timing, the earliest departure is {departs}, with arrival in {dcity} around {arrives}.",
                 "On timing: the earliest flight leaves on {departs} and {they} should land in {dcity} around "
                 "{arrives}."],
    "cutoff": "The exact drop-off cut-off at {ocity} depends on the flight, so I'll confirm it with the airline as soon "
              "as it's booked; it's usually the day before departure.",
    "space": "Space is confirmed by the airline at booking, so I'll secure it as soon as you give me the go-ahead.",
    "awb": "All lots travel together as one consignment under a single air waybill, as you asked.",
    "dg": "As these are dangerous goods, they fly as DG cargo, so I'll need the Shipper's Declaration for Dangerous "
          "Goods and the MSDS from you before pickup.",
    "price": ["All in, that comes to {amount}{incl}.", "The all-in price is {amount}{incl}.",
              "Your all-in price for this is {amount}{incl}."],
    "incl_town": ", including the truck from {town} to the airport", "incl_door": ", including the pickup",
    "cta": {"formal": ["If this suits you, simply reply to this email and I will book it right away.",
                       "Should you wish to go ahead, a short reply to this email is all I need to make the booking."],
            "neutral": ["If that works for you, just reply to this email and I'll book it right away.",
                        "Just reply to this email if you'd like to go ahead, and I'll take care of the booking."],
            "casual": ["If that works for you, just reply and I'll get it booked.",
                       "Just hit reply if you'd like to go ahead and I'll book it straight away."]},
    "nice_day": "Enjoy the rest of your day too.",
    "bye": {"formal": "Kind regards,", "neutral": "Best regards,", "casual": "Best,"},
    "bye_from": "Best wishes back to {city},",
    "days": ("{n} day", "{n} days"), "it": ("it", "it", "it's", "It"), "them": ("them", "they", "they're", "They"),
}
DE = {
    "thanks": {"formal": ["vielen Dank für Ihre Anfrage{ref}.", "herzlichen Dank für Ihre Anfrage{ref}."],
               "neutral": ["vielen Dank für Ihre Anfrage{ref}.", "danke für Ihre Anfrage{ref}."],
               "casual": ["danke für Ihre Anfrage{ref}.", "vielen Dank für die Anfrage{ref}."]},
    "week": ["danke, hier ist alles gut, und ich hoffe, Ihre Woche läuft auch gut.",
             "danke der Nachfrage, bei mir läuft alles gut, und ich hoffe, bei Ihnen auch."],
    "sorry": ["danke für die Abholadresse, damit habe ich alles.", "kein Problem, danke für die Abholadresse."],
    "ask": {"cheapest": "die günstigste Option", "fastest": "die schnellste Option"},
    "offer": ["für Ihre Sendung ({goods}) ist {ask} ein Flug mit {carrier} von {o} nach {d}.",
              "ich habe die Optionen für Ihre Sendung ({goods}) verglichen: {ask} ist {carrier} von {o} nach {d}."],
    "door": ["Wir holen die Ware am {start} {at_town} ab, der Flug geht am {departs} und die Sendung sollte etwa am "
             "{arrives} in {dcity} landen.",
             "Unser Lkw holt am {start} {at_town} ab, der Abflug ist am {departs}, Ankunft in {dcity} etwa am "
             "{arrives}."],
    "port": ["Der Flug ab {ocity} geht am {departs}, Ankunft in {dcity} etwa am {arrives}, also {n} Laufzeit.",
             "Abflug ab {ocity} ist am {departs}, die Sendung sollte etwa am {arrives} in {dcity} sein ({n} Laufzeit)."],
    "earliest": ["Zum Zeitplan: Der früheste Abflug ist am {departs}, Ankunft in {dcity} etwa am {arrives}.",
                 "Frühestmöglich geht der Flug am {departs}, die Ankunft in {dcity} wäre etwa am {arrives}."],
    "cutoff": "Den genauen Annahmeschluss in {ocity} bestätige ich Ihnen mit der Buchung, sobald die Airline den Flug "
              "festlegt; üblicherweise ist er am Vortag des Abflugs.",
    "space": "Den Platz bestätigt die Airline bei der Buchung, ich sichere ihn, sobald Sie mir grünes Licht geben.",
    "awb": "Alle Partien reisen wie gewünscht zusammen als eine Sendung unter einem Luftfrachtbrief.",
    "dg": "Da es sich um Gefahrgut handelt, fliegt die Sendung als DG-Fracht: Bitte senden Sie mir vor der Abholung "
          "die Shipper's Declaration for Dangerous Goods und das Sicherheitsdatenblatt (MSDS).",
    "price": ["Der All-in-Preis beträgt {amount}{incl}.", "Alles inklusive kostet die Sendung {amount}{incl}."],
    "incl_town": ", inklusive Lkw von {town} zum Flughafen", "incl_door": ", inklusive Abholung",
    "cta": {"formal": ["Wenn das für Sie passt, antworten Sie einfach auf diese E-Mail und ich buche sofort.",
                       "Möchten Sie buchen, genügt eine kurze Antwort auf diese E-Mail."],
            "neutral": ["Wenn das für Sie passt, antworten Sie einfach kurz und ich kümmere mich um die Buchung.",
                        "Antworten Sie einfach auf diese E-Mail, dann buche ich gleich."],
            "casual": ["Wenn das passt, einfach kurz antworten und ich buche.",
                       "Kurze Antwort genügt, dann buche ich direkt."]},
    "nice_day": "Ihnen auch noch einen schönen Tag.",
    "bye": {"formal": "Mit freundlichen Grüßen", "neutral": "Viele Grüße", "casual": "Viele Grüße"},
    "bye_from": "Viele Grüße zurück nach {city}",
    "days": ("{n} Tag", "{n} Tage"), "it": ("sie",) * 3 + ("Sie",), "them": ("sie",) * 3 + ("Sie",),
}


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def a_quote_text(rfq: dict, option: dict, mail_body: str | None = None, today: date | None = None) -> str:
    f = _facts(rfq, option, today or date.today())
    lang, L = f["language"], (DE if f["language"] == "de" else EN)
    body = latest_text(mail_body or "")
    pickup_line = (rfq.get("pickup") or {}).get("address") or ""
    style = tone(body)
    seed = f"{rfq.get('customer_reference')}{rfq.get('origin')}{rfq.get('destination')}{option.get('total')}"
    start, departs, arrives = f["_dates"]
    it = L["it"] if f["pieces"] == 1 else L["them"]
    ref = f" ({f['reference']})" if f["reference"] else ""

    if SORRY.search(body) or SORRY.search(pickup_line):
        opener = _pick(L["sorry"], seed, "sorry")
    elif HOPE_WEEK.search(body):
        opener = _pick(L["week"], seed, "week")
    else:
        opener = _pick(L["thanks"][style], seed, "thanks").format(ref=ref)
        ref = ""
    if ref:
        opener += f" {'Ihre Referenz' if lang == 'de' else 'Your reference'}: {f['reference']}."

    if lang == "de":
        goods = f"{f['pieces']} {'Packstück' if f['pieces'] == 1 else 'Packstücke'}" + (f", {f['goods']}" if f["goods"]
                                                                                         else "")
    elif f["pieces"] == 1:
        goods = f["goods"] or "shipment"
    else:
        goods = f"{f['pieces']} pieces" + (f" of {f['goods']}" if f["goods"] else "")
    ask = L["ask"].get(f["ask"], L["ask"]["cheapest"])
    ocity, dcity = _city(rfq.get("origin"), lang), _city(rfq.get("destination"), lang)
    v = {"goods": goods, "ask": ask, "Ask": _cap(ask), "carrier": f["carrier"], "o": _place(rfq.get("origin"), lang),
         "d": _place(rfq.get("destination"), lang), "ocity": ocity, "dcity": dcity, "start": f["pickup_or_handover_date"],
         "departs": f["departure_date"], "arrives": f["arrival_date"],
         "n": L["days"][0 if f["transit_days"] == 1 else 1].format(n=f["transit_days"]),
         "them": it[0], "they": it[1], "they're": it[2], "They": it[3],
         "at_town": f"in {f['pickup_town']}" if f["pickup_town"] else ("bei Ihnen" if lang == "de" else
                                                                         "from your site")}
    offer = _cap(_pick(L["offer"], seed, "offer").format(**v))  # mid-paragraph; only the de opener stays lowercase
    if ASK_DEPART.search(body) or ASK_ARRIVE.search(body):
        timing = _pick(L["earliest"], seed, "earliest").format(**v)
        if f["door_pickup"]:
            pick = ("Wir holen die Ware am {start} {at_town} ab. " if lang == "de" else
                    "We'd collect {them} {at_town} on {start}. ").format(**v)
            timing = pick + timing
    else:
        timing = _pick(L["door" if f["door_pickup"] else "port"], seed, "plan").format(**v)
    extra = [L[key].format(**v) for key, pattern in (("awb", ONE_AWB), ("space", ASK_SPACE)) if pattern.search(body)]
    if ASK_CUTOFF.search(body) and not f["door_pickup"]:
        extra.append(L["cutoff"].format(**v))
    first = " ".join([opener, offer, timing, *extra])

    incl = (L["incl_town"].format(town=f["pickup_town"]) if f["pickup_town"] else L["incl_door"]) if f["door_pickup"] \
        else ""
    price = _pick(L["price"], seed, "price").format(amount=_amount(option), incl=incl)
    close = [price, _pick(L["cta"][style], seed, "cta")]
    if NICE_DAY.search(body):
        close.append(L["nice_day"])
    m = GREETINGS_FROM.search(body)
    bye = L["bye_from"].format(city=m.group(1)) if m else L["bye"][style]
    hi = greeting(rfq.get("contact_name"), style, lang)
    paragraphs = [hi, first if lang == "de" else _cap(first), *([L["dg"]] if f["dangerous_goods"] else []),
                  " ".join(close), f"{bye}\n{SIGNER}\n{TEAM}"]
    return "\n\n".join(paragraphs)


# ---- variant b: one small LLM call, checked by code ----------------------------------------------------------------

B_SYSTEM = """You are Lena, an experienced air freight forwarder at Leylü Air Freight, replying to a customer's quote \
request. Write the email in the language given by "language" (en = English, de = German with "Sie").
Rules:
- Start with a greeting that mirrors the customer's tone ("tone": formal → "Dear Ms/Mr Surname" if "title" is given, \
else "Dear Firstname Surname"; neutral → "Hello Firstname"; casual → "Hi Firstname").
- Write exactly the placeholder {PRICE} where the all-in price goes, once. {PRICE} already includes the currency \
("EUR 1,234.56"): never write the currency next to it. Never write any other amount, weight, \
volume, percentage or clock time.
- The only numbers you may use are those inside the given facts (dates, pieces, transit_days, pickup_postcode, \
reference). Do not invent flight numbers, times, routings, stops or services.
- Answer the customer's explicit questions only from the facts. For drop-off or cut-off times say you will confirm \
the exact cut-off with the airline once it is booked, usually the day before departure.
- If the customer made small talk, acknowledge it once, briefly and naturally.
- If dangerous_goods is true, ask for the "Shipper's Declaration for Dangerous Goods" and the "MSDS" (these exact words).
- Mention the goods and, if given, the pickup town naturally. End by saying they can just reply to this email to book.
- 60 to 120 words, plain text paragraphs, no bullet lists, no subject line, no "I hope this email finds you well", \
at most one exclamation mark. End with a short closing phrase (e.g. "Best regards,"). Do NOT write your name or \
company: the signature is added."""
B_SCHEMA = {"type": "object", "properties": {"mail": {"type": "string"}}, "required": ["mail"],
            "additionalProperties": False}
REPLY_CUE = re.compile(r"\brepl|\bantwort", re.I)
B_STATS = {"calls": 0, "cost_usd": 0.0, "seconds": 0.0, "fallbacks": 0}  # read by the comparison script


def b_facts(rfq: dict, option: dict, mail_body: str | None, today: date) -> dict:
    f = {k: v for k, v in _facts(rfq, option, today).items() if not k.startswith("_")}
    body = latest_text(mail_body or "")
    name = (rfq.get("contact_name") or "").split()
    pickup_line = (rfq.get("pickup") or {}).get("address") or ""
    return {**f, "customer_mail": body[:1500], "tone": tone(body),
            "first_name": name[0] if name else None, "surname": name[-1] if len(name) > 1 else None,
            "title": _title(name[0], f["language"]) if name else None,
            "customer_follow_up": pickup_line if SORRY.search(pickup_line) else None}


def insert_price(draft: str, option: dict) -> str:
    """{PRICE} → "EUR 1,856.00". The model likes to add the currency again ("{PRICE} EUR", "{PRICE} all-in in EUR")."""
    cur = re.escape(option["currency"])
    draft = re.sub(rf"\{{PRICE\}}\s+all-in\s+in\s+{cur}\b", "{PRICE} all-in", draft)
    return re.sub(rf"(?:\b{cur}\s+)?\{{PRICE\}}(?:\s+{cur}\b)?", _amount(option), draft)


def check_b(text: str, option: dict, facts: dict) -> list[str]:
    """Why the model's mail can't go out ([] = fine). text has the amount already inserted."""
    problems = []
    amount = f"{option['total']:,.2f}"
    if gate.MONEY.findall(text) != [amount]:
        problems.append(f"amounts {gate.MONEY.findall(text)}")
    if option["currency"] not in text:
        problems.append("currency missing")
    if re.search(rf"{re.escape(amount)}\s+{re.escape(option['currency'])}\b|\b(\w+) \1\b", text):
        problems.append("doubled currency or word")
    allowed = {str(facts["pieces"]), str(facts["transit_days"])}
    for key in ("pickup_or_handover_date", "departure_date", "arrival_date", "pickup_postcode", "reference"):
        allowed |= set(re.findall(r"\d+", str(facts.get(key) or "")))
    unknown = [n for n in re.findall(r"\d+", text.replace(amount, "")) if n not in allowed]
    if unknown:
        problems.append(f"unknown numbers {unknown}")
    if facts["dangerous_goods"] and not ("MSDS" in text and "Dangerous Goods" in text):
        problems.append("DG papers not asked")
    if not REPLY_CUE.search(text):
        problems.append("no reply-to-book")
    if re.search(r"^\s*[-*•]\s", text, re.M):
        problems.append("bullet list")
    if not 40 <= len(text.split()) <= 160:
        problems.append(f"{len(text.split())} words")
    return problems


def b_quote_text(rfq: dict, option: dict, mail_body: str | None = None, today: date | None = None) -> str:
    today = today or date.today()
    try:
        facts = b_facts(rfq, option, mail_body, today)
        started = time.monotonic()
        data, cost = llm.chat_json("quote_mail", B_SYSTEM, json.dumps(facts, ensure_ascii=False), B_SCHEMA)
        B_STATS["calls"] += 1
        B_STATS["cost_usd"] += cost
        B_STATS["seconds"] += time.monotonic() - started
        draft = data["mail"].strip()
        if draft.count("{PRICE}") != 1:
            raise ValueError(f"{draft.count('{PRICE}')} price placeholders")
        lines = draft.splitlines()
        while lines and (not lines[-1].strip() or re.search(r"\b(Lena|Leylü)\b", lines[-1])):
            lines.pop()  # the model signed anyway: the code adds the signature
        text = insert_price("\n".join(lines), option) + f"\n{SIGNER}\n{TEAM}"
        if problems := check_b(text, option, facts):
            raise ValueError("; ".join(problems))
        return text
    except Exception as error:  # never lose a quote over wording: the code-only mail instead
        B_STATS["fallbacks"] += 1
        print(f"quote mail b failed, a instead: {type(error).__name__}: {error}")
        return a_quote_text(rfq, option, mail_body, today)
