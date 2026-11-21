"""Quote mails that read like Lena wrote them (5U's per-round "humanity" bonus). QUOTE_STYLE=a or b, English + German.

a (code, $0): mirrors the customer's tone (Dear Ms X / Hello Tobias / Hi Klaus), answers their questions from our data
  (earliest departure and arrival, drop-off cut-off, one air waybill, space), replies to small talk once, names their
  goods and pickup town, and varies its sentences per request (seeded, deterministic).
b (one gpt-6-luna call): the model writes the body with {PRICE} from a facts JSON; code inserts the amount and checks
  it (one amount, only numbers from the facts, DG papers, how to accept). Any failure → a.

Hard rules for both: exactly one money amount (the all-in total, currency named); dates, times and airlines only from
the RFQ and the chosen option; DG → ask for the Shipper's Declaration for Dangerous Goods and the MSDS; signed "Lena Hartmann, Air Export | Leylü Air Freight".
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

SIGNER = "Lena Hartmann"  # + "Air Export | Leylü Air Freight" (EN/DE["team"]): no phone, no invented email
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
    """Always "neutral": our mails never copy the sender's style, formal, casual, slang or shouting (Julien, 22 Nov)."""
    return "neutral"


TITLE_WORDS = {"mr": ("Mr", "Herr"), "mrs": ("Mrs", "Frau"), "ms": ("Ms", "Frau"), "herr": ("Mr", "Herr"),
               "frau": ("Ms", "Frau"), "dr": ("Dr", "Dr.")}


def _title(name: str | None, text: str, lang: str) -> str | None:
    """A title only when the customer wrote one next to their own surname ("Dr. Eva Huber", "Herr Kessler"): a title
    guessed from a first name can misgender a person, so otherwise none ("Dear Jonas Kessler")."""
    parts = (name or "").split()
    if len(parts) < 2 or not text:
        return None
    m = re.search(rf"\b(Mr|Mrs|Ms|Herr|Frau|Dr)\.?\s+(?:\w+\s+)?{re.escape(parts[-1])}\b", text, re.I)
    if not m:
        return None
    en, de = TITLE_WORDS[m.group(1).lower()]
    return de if lang == "de" else en


def greeting(name: str | None, style: str, lang: str, text: str = "") -> str:
    parts = (name or "").split()
    first, last = (parts[0], parts[-1]) if parts else (None, None)
    title = _title(name, text, lang)
    if lang == "de":
        if style == "formal":
            if title and len(parts) > 1:
                return (f"Sehr geehrte{'r' if title == 'Herr' else ''} {title} {last}," if title in ("Herr", "Frau")
                        else f"Guten Tag {title} {last},")
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
        "currency": option["currency"], "gross_kg": gross_kg(rfq), "_dates": (start, departs, arrives),
    }


def _amount(option: dict) -> str:
    return f"{option['currency']} {option['total']:,.2f}"


# ---- variant a: code only ------------------------------------------------------------------------------------------
# 5U's jury reads every team's quote round after round: one sentence skeleton reads like a template after a few rounds.
# Each part of the mail comes from its own pool and rotates with the 6-minute round (_round), so consecutive quotes
# never share an opening, and the pools (different sizes) don't line up into the same combination either.

ATTACHED = re.compile(r"\battach|\benclos|\banbei\b|im anhang|beigefügt", re.I)
DOCS = [(re.compile(r"packing spec", re.I), "packing specification", "Packspezifikation"),
        (re.compile(r"packing list|packliste", re.I), "packing list", "Packliste"),
        (re.compile(r"letter of instruction|\bSLI\b", re.I), "shipper's letter of instruction", "Shipper's Letter of Instruction"),
        (re.compile(r"commercial invoice|handelsrechnung", re.I), "commercial invoice", "Handelsrechnung"),
        (re.compile(r"data ?sheet|datenblatt", re.I), "data sheet", "Datenblatt")]
MASS = {"equipment", "material", "materials", "machinery", "furniture", "cargo", "goods", "supplies", "adhesives",
        "chemicals", "textiles", "electronics", "cosmetics", "pharmaceuticals", "coatings", "paints", "lubricants",
        "plastics", "clothing", "apparel", "hardware", "software", "freight", "merchandise", "foodstuffs"}
NUM_EN = "zero one two three four five six seven eight nine ten eleven twelve".split()
NUM_DE = "null ein zwei drei vier fünf sechs sieben acht neun zehn elf zwölf".split()

EN = {
    # (no attachment, attachment named): the customer's documents are acknowledged in the opening itself
    "open": {"formal": [("Thank you for your enquiry{ref}.", "Thank you for your enquiry{ref} and for sending the {doc}."),
                        ("Many thanks for your request{ref}.", "Many thanks for your request{ref}; the {doc} you attached was a great help."),
                        ("Thank you for thinking of us for this shipment{ref}.", "Thank you for thinking of us for this shipment{ref}, and for attaching the {doc}."),
                        ("I'm happy to help with this one{ref}.", "I'm happy to help with this one{ref}, and the {doc} had everything I needed."),
                        ("Here is our offer for your request{ref}.", "Thank you for the {doc}; here is our offer for your request{ref}."),
                        ("I've had a look at your request{ref}.", "I've gone through your request{ref} and the {doc}, thank you for sending it."),
                        ("Thanks for getting in touch about this shipment{ref}.", "Thanks for getting in touch{ref}, and for sending the {doc} straight away."),
                        ("I've put together a quote for your request{ref}.", "I've put together a quote for your request{ref} from the {doc} you sent, thank you."),
                        ("Thank you for the clear details{ref}.", "Thank you for the clear details and the {doc}{ref}."),
                        ("Happy to quote this for you{ref}.", "Happy to quote this for you{ref}, and thank you for the {doc}.")],
             "casual": [("Thanks for sending this over{ref}.", "Thanks for sending this over{ref}, and for the {doc}."),
                        ("Thanks for the request{ref}, happy to help.", "Thanks for the request{ref} and the {doc}, happy to help."),
                        ("Got your request{ref}, here's what I can do.", "Got your request{ref} and the {doc}, here's what I can do."),
                        ("Thanks for thinking of us{ref}.", "Thanks for thinking of us{ref}, and for attaching the {doc}."),
                        ("Happy to help with this one{ref}.", "Happy to help with this one{ref}, thanks for the {doc}."),
                        ("I've had a look at this for you{ref}.", "I've had a look at this and the {doc} for you{ref}."),
                        ("Here's the price you asked for{ref}.", "Here's the price you asked for{ref}, and thanks for the {doc}."),
                        ("Here's my offer for this one{ref}.", "Here's my offer for this one{ref}, thanks for the {doc}."),
                        ("Quick turnaround on this one{ref}.", "Quick turnaround on this one{ref}, thanks to the {doc}."),
                        ("Thanks for checking with us{ref}.", "Thanks for checking with us{ref} and for the {doc}.")]},
    "doc_after": "Thanks also for the {doc}.",
    # small talk: first part × second part (5 × 2) so the same customer's "hope your week…" gets ten different answers
    "week": (["Thanks, all good here", "All good on my side, thanks", "Thanks for asking, all well here",
              "Busy but good here, thanks", "All fine here, thank you"],
             [", and I hope your week is going well too.", "; I hope the same goes for you."]),
    "sorry": (["No problem at all", "No worries at all", "Not a problem", "Thanks for following up",
               "Many thanks for that"],
              [", the pickup address was all I needed.", ", with the pickup location I have everything."]),
    "ask": {"cheapest": "the most economical option", "fastest": "the fastest option"},
    "offer": ["For your {goods}, {ask} is {carrier} from {o} to {d}.",
              "Looking at the options for your {goods}, {ask} is {carrier}, flying {o} to {d}.",
              "{Ask} for your {goods} is {carrier} from {o} to {d}.",
              "Your {goods} would fly with {carrier} from {o} to {d}, which is {ask} right now.",
              "I'd put your {goods} on {carrier}, routing {o} to {d}; that's {ask} we have.",
              "For your {goods} I can offer {carrier} from {o} to {d}, {ask} at the moment."],
    "door": ["We'd collect {them} {at_town} on {start}, the flight leaves on {departs} and {they} should land in "
             "{dcity} around {arrives}.",
             "Our truck can pick {them} up {at_town} on {start}; {they} then fly out on {departs} and should reach "
             "{dcity} around {arrives}.",
             "Pickup {at_town} would be on {start}, with the flight on {departs} and arrival in {dcity} expected around "
             "{arrives}.",
             "If we collect {at_town} on {start}, {they} can fly on {departs} and should be in {dcity} around {arrives}.",
             "The plan would be collection {at_town} on {start} and departure on {departs}, so {they} should land in "
             "{dcity} around {arrives}."],
    "port": ["Once {they're} at {ocity} airport, the flight leaves on {departs} and {they} should land in {dcity} "
             "around {arrives}, so {n} in transit.",
             "{They} would fly out of {ocity} on {departs} and should be in {dcity} around {arrives}, {n} in transit.",
             "The flight leaves {ocity} on {departs}, with arrival in {dcity} expected around {arrives} ({n} in transit).",
             "Departure from {ocity} would be on {departs}, landing in {dcity} around {arrives}, which is {n} in transit.",
             "If you hand {them} over at {ocity} airport by {start}, {they} fly on {departs} and should be in {dcity} "
             "around {arrives}."],
    "earliest": ["As for timing, the earliest departure is {departs}, with arrival in {dcity} around {arrives}.",
                 "On timing: the earliest flight leaves on {departs} and {they} should land in {dcity} around {arrives}.",
                 "The earliest I can get {them} out is {departs}, arriving in {dcity} around {arrives}.",
                 "To your timing question: first departure is {departs}, and {they} should reach {dcity} around {arrives}.",
                 "The earliest flight goes on {departs}; arrival in {dcity} should be around {arrives}."],
    "pickup_first": "We'd collect {them} {at_town} on {start}.",
    "deadline": ["That gets {them} there ahead of your {deadline} deadline.",
                 "That's comfortably before {deadline}, when you need {them} there.",
                 "So {they} arrive in good time for your {deadline} deadline."],
    "excluded": ["As you asked, I've left out the airline you ruled out.",
                 "The airline you ruled out isn't in this offer, as requested.",
                 "I've kept the airline you ruled out off the list, as you asked."],
    "cutoff": "The exact drop-off cut-off at {ocity} depends on the flight, so I'll confirm it with the airline as soon "
              "as it's booked; it's usually the day before departure.",
    "space": "Space is confirmed by the airline at booking, so I'll secure it as soon as you give me the go-ahead.",
    "awb": "All lots travel together as one consignment under a single air waybill, as you asked.",
    "dg": "As these are dangerous goods, they fly as DG cargo, so I'll need the Shipper's Declaration for Dangerous "
          "Goods and the MSDS from you before pickup.",
    "price": ["All in, that comes to {amount}{incl}.", "The all-in price is {amount}{incl}.",
              "Your all-in price is {amount}{incl}.", "In total, it comes to {amount}{incl}.",
              "I can do this for {amount} all in{incl}.", "The total comes to {amount} all in{incl}."],
    "incl_town": [", including the truck from {town} to the airport", ", pickup in {town} included",
                  ", with the collection in {town} included"],
    "incl_door": [", including the pickup", ", pickup included", ", with the collection included"],
    "subject": ["That's subject to space when we book.", "That's subject to space being available when I book.",
                "The only proviso is space on the flight, which the airline confirms when we book.",
                "It only depends on space on the flight when we book.",
                "That's subject to the airline confirming space when we book."],
    "cta": {"formal": ["If this suits you, simply reply to this email and I will book it right away.",
                       "Should you wish to go ahead, a short reply to this email is all I need to make the booking.",
                       "If you are happy with this, just reply to this email and I'll arrange the booking.",
                       "A reply to this email is all it takes to confirm, and I'll take it from there.",
                       "Let me know by replying to this email if you'd like to proceed, and I'll book it straight away."],
            "neutral": ["If that works for you, just reply to this email and I'll book it right away.",
                        "Just reply to this email if you'd like to go ahead, and I'll take care of the booking.",
                        "If you'd like to book, a quick reply to this email is enough.",
                        "Reply to this email whenever you're ready and I'll get it booked.",
                        "If it suits you, just reply and I'll sort out the booking."],
            "casual": ["If that works for you, just reply and I'll get it booked.",
                       "Just hit reply if you'd like to go ahead and I'll book it straight away.",
                       "Give me a quick reply if you're happy and I'll lock it in.",
                       "Reply with a yes and I'll take care of the rest.",
                       "If that sounds good, just reply and it's booked."]},
    "nice_day": "Enjoy the rest of your day too.",
    "bye": {"formal": ["Kind regards,", "Best regards,", "With kind regards,", "Many thanks and kind regards,",
                       "Yours sincerely,"],
            "neutral": ["Best regards,", "Kind regards,", "Best wishes,", "Many thanks,", "All the best,"],
            "casual": ["Best,", "Cheers,", "All the best,", "Speak soon,", "Thanks again,"]},
    "bye_from": "Best wishes back to {city},",
    "team": "Air Export | Leylü Air Freight",
    "days": ("{n} day", "{n} days"), "it": ("it", "it", "it's", "It"), "them": ("them", "they", "they're", "They"),
}
DE = {
    "open": {"formal": [("vielen Dank für Ihre Anfrage{ref}.", "vielen Dank für Ihre Anfrage{ref} und die {doc}."),
                        ("herzlichen Dank für Ihre Anfrage{ref}.", "herzlichen Dank für Ihre Anfrage{ref}; die beigefügte {doc} hat sehr geholfen."),
                        ("gern mache ich Ihnen ein Angebot{ref}.", "gern mache ich Ihnen ein Angebot{ref}, danke auch für die {doc}."),
                        ("ich habe mir Ihre Anfrage{ref} angesehen und habe eine gute Option für Sie.", "ich habe mir Ihre Anfrage{ref} und die {doc} angesehen und habe eine gute Option für Sie."),
                        ("danke, dass Sie bei dieser Sendung an uns gedacht haben{ref}.", "danke, dass Sie bei dieser Sendung an uns gedacht haben{ref}, und für die {doc}."),
                        ("hier ist unser Angebot zu Ihrer Anfrage{ref}.", "danke für die {doc}; hier ist unser Angebot zu Ihrer Anfrage{ref}.")]},
    "doc_after": "Danke auch für die {doc}.",
    "week": (["danke, hier ist alles gut", "danke der Nachfrage, bei mir läuft alles gut", "danke, hier läuft alles bestens",
              "viel zu tun, aber alles gut hier, danke", "danke, alles bestens"],
             [", und ich hoffe, Ihre Woche läuft auch gut.", "; ich hoffe, bei Ihnen auch."]),
    "sorry": (["kein Problem", "gar kein Problem", "danke für die Abholadresse", "vielen Dank für die Nachricht",
               "danke für die schnelle Rückmeldung"],
              [", damit habe ich alles.", ", mit der Abholadresse ist alles komplett."]),
    "ask": {"cheapest": "die günstigste Option", "fastest": "die schnellste Option"},
    "offer": ["für {goods} ist {ask} ein Flug mit {carrier} von {o} nach {d}.",
              "ich habe die Optionen für {goods} verglichen: {ask} ist {carrier} von {o} nach {d}.",
              "{Ask} für {goods} ist {carrier} von {o} nach {d}.",
              "{Ask} für {goods}: {carrier} von {o} nach {d}.",
              "für {goods} kann ich Ihnen {carrier} von {o} nach {d} anbieten, derzeit {ask}."],
    "door": ["Wir holen die Ware am {start} {at_town} ab, der Flug geht am {departs} und die Sendung sollte etwa am "
             "{arrives} in {dcity} landen.",
             "Unser Lkw holt am {start} {at_town} ab, der Abflug ist am {departs}, Ankunft in {dcity} etwa am {arrives}.",
             "Die Abholung {at_town} wäre am {start}, der Flug am {departs} und die Ankunft in {dcity} etwa am {arrives}.",
             "Wenn wir am {start} {at_town} abholen, fliegt die Sendung am {departs} und ist etwa am {arrives} in {dcity}.",
             "Geplant ist die Abholung {at_town} am {start} und der Abflug am {departs}; in {dcity} sollte die Sendung "
             "etwa am {arrives} sein."],
    "port": ["Der Flug ab {ocity} geht am {departs}, Ankunft in {dcity} etwa am {arrives}, also {n} Laufzeit.",
             "Abflug ab {ocity} ist am {departs}, die Sendung sollte etwa am {arrives} in {dcity} sein ({n} Laufzeit).",
             "Die Sendung fliegt am {departs} ab {ocity} und sollte etwa am {arrives} in {dcity} landen.",
             "Ab {ocity} geht es am {departs} los, die Ankunft in {dcity} ist etwa am {arrives} ({n} Laufzeit).",
             "Mit Abflug am {departs} ab {ocity} ist die Sendung etwa am {arrives} in {dcity}."],
    "earliest": ["Zum Zeitplan: Der früheste Abflug ist am {departs}, Ankunft in {dcity} etwa am {arrives}.",
                 "Frühestmöglich geht der Flug am {departs}, die Ankunft in {dcity} wäre etwa am {arrives}.",
                 "Der früheste Flug geht am {departs}, in {dcity} ist die Sendung etwa am {arrives}.",
                 "Zu Ihrer Frage nach dem Zeitplan: Abflug frühestens am {departs}, Ankunft in {dcity} etwa am {arrives}.",
                 "Am schnellsten geht es mit Abflug am {departs} und Ankunft in {dcity} etwa am {arrives}."],
    "pickup_first": "Wir holen die Ware am {start} {at_town} ab.",
    "deadline": ["Damit ist die Sendung vor Ihrem Termin am {deadline} da.",
                 "Das liegt gut vor Ihrem Termin am {deadline}.",
                 "So ist die Ware rechtzeitig vor dem {deadline} am Ziel."],
    "excluded": ["Wie gewünscht habe ich die von Ihnen ausgeschlossene Airline nicht angefragt.",
                 "Die von Ihnen ausgeschlossene Airline bleibt wie gewünscht außen vor.",
                 "Wie besprochen ist die von Ihnen ausgeschlossene Airline nicht dabei."],
    "cutoff": "Den genauen Annahmeschluss in {ocity} bestätige ich Ihnen mit der Buchung, sobald die Airline den Flug "
              "festlegt; üblicherweise ist er am Vortag des Abflugs.",
    "space": "Den Platz bestätigt die Airline bei der Buchung, ich sichere ihn, sobald Sie mir grünes Licht geben.",
    "awb": "Alle Partien reisen wie gewünscht zusammen als eine Sendung unter einem Luftfrachtbrief.",
    "dg": "Da es sich um Gefahrgut handelt, fliegt die Sendung als DG-Fracht: Bitte senden Sie mir vor der Abholung "
          "die Shipper's Declaration for Dangerous Goods und das Sicherheitsdatenblatt (MSDS).",
    "price": ["Der All-in-Preis beträgt {amount}{incl}.", "Alles inklusive kostet die Sendung {amount}{incl}.",
              "Insgesamt, alles inklusive, sind es {amount}{incl}.", "Ihr All-in-Preis: {amount}{incl}.",
              "Komplett kostet das {amount}{incl}."],
    "incl_town": [", inklusive Lkw von {town} zum Flughafen", ", die Abholung in {town} inklusive"],
    "incl_door": [", inklusive Abholung", ", Abholung inklusive"],
    "subject": ["Wie immer vorbehaltlich Platz bei der Buchung.", "Das gilt vorbehaltlich freier Kapazität bei der Buchung.",
                "Einziger Vorbehalt ist der Platz im Flug, den die Airline bei der Buchung bestätigt.",
                "Wie üblich hängt es vom Platz zum Zeitpunkt der Buchung ab.",
                "Vorbehaltlich der Platzbestätigung durch die Airline bei der Buchung."],
    "cta": {"formal": ["Wenn das für Sie passt, antworten Sie einfach auf diese E-Mail und ich buche sofort.",
                       "Möchten Sie buchen, genügt eine kurze Antwort auf diese E-Mail.",
                       "Wenn Sie einverstanden sind, antworten Sie einfach kurz, dann veranlasse ich die Buchung.",
                       "Eine Antwort auf diese E-Mail genügt, und ich kümmere mich um alles Weitere.",
                       "Geben Sie mir mit einer Antwort auf diese E-Mail Bescheid, dann buche ich umgehend."],
            "casual": ["Wenn das passt, einfach kurz antworten und ich buche.",
                       "Kurze Antwort genügt, dann buche ich direkt.",
                       "Wenn Sie zufrieden sind, einfach antworten, dann geht die Buchung raus.",
                       "Antworten Sie einfach auf diese E-Mail, dann buche ich gleich.",
                       "Sagen Sie mir per Antwort Bescheid, dann kümmere ich mich um die Buchung."]},
    "nice_day": "Ihnen auch noch einen schönen Tag.",
    "bye": {"formal": ["Mit freundlichen Grüßen", "Freundliche Grüße", "Beste Grüße", "Mit besten Grüßen",
                       "Herzliche Grüße"],
            "casual": ["Viele Grüße", "Beste Grüße", "Herzliche Grüße", "Liebe Grüße", "Schöne Grüße"]},
    "bye_from": "Viele Grüße zurück nach {city}",
    "team": "Luftfracht Export | Leylü Air Freight",
    "days": ("{n} Tag", "{n} Tage"), "it": ("sie",) * 3 + ("Sie",), "them": ("sie",) * 3 + ("Sie",),
}


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _round() -> int:
    """The 6-minute round we're in (one RFQ per round): consecutive quotes get consecutive pool entries."""
    return int(time.time() // 360)


def _rot(options: list, seq: int, key: str):
    """Entry `seq` of the pool, shifted per pool so the pools don't move in lockstep."""
    return options[(seq + zlib.crc32(key.encode())) % len(options)]


def _tone_pool(pool: dict, style: str) -> list:
    return pool.get(style) or pool["formal"]  # neutral → formal wording where a pool has no neutral entries


def gross_kg(rfq: dict) -> int | None:
    pieces = rfq.get("pieces") or []
    if not pieces or any(p.get("weight_kg") is None for p in pieces):
        return None
    return round(sum(int(p.get("count") or 1) * p["weight_kg"] for p in pieces)) or None


def _singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if re.search(r"(ch|sh|x|ss)es$", word):
        return word[:-2]
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def goods_phrase(count: int, goods: str, kg: int | None, lang: str) -> str:
    """ "four handheld measuring devices (378 kg)", "twelve pieces of sports equipment (349 kg)": what the price is for.
    Numbers up to twelve as words; "pieces of" only for goods you can't count. No decimals (one amount per mail)."""
    weight = f" ({kg} kg)" if kg else ""
    if lang == "de":
        num = NUM_DE[count] if count <= 12 else str(count)
        unit = "Ihr Packstück" if count == 1 else f"Ihre {num} Packstücke"
        return unit + (f" {goods}" if goods else "") + weight
    num = NUM_EN[count] if count <= 12 else str(count)
    head = re.split(r"\s+(?:for|of|with|from|in)\s+", goods)[0].split()[-1].lower() if goods else ""
    countable = head.endswith("s") and not head.endswith("ss") and head not in MASS
    if not goods:
        return ("shipment" if count == 1 else f"{num} pieces") + weight
    if countable:
        if count == 1:
            words = re.split(r"(\s+(?:for|of|with|from|in)\s+)", goods, maxsplit=1)
            first = words[0].rsplit(" ", 1)
            words[0] = " ".join([*first[:-1], _singular(first[-1])])
            return "".join(words) + weight
        return f"{num} {goods}{weight}"
    return (f"{goods}" if count == 1 else f"{num} pieces of {goods}") + weight


def _doc(body: str, lang: str) -> str | None:
    """The document the customer attached ("packing specification"), when the mail says it is attached."""
    if not ATTACHED.search(body):
        return None
    for pattern, en, de in DOCS:
        if pattern.search(body):
            return de if lang == "de" else en
    return None


def a_quote_text(rfq: dict, option: dict, mail_body: str | None = None, today: date | None = None,
                 seq: int | None = None) -> str:
    f = _facts(rfq, option, today or date.today())
    lang, L = f["language"], (DE if f["language"] == "de" else EN)
    body = latest_text(mail_body or "")
    pickup_line = (rfq.get("pickup") or {}).get("address") or ""
    style = tone(body)
    seq = _round() if seq is None else seq
    start, departs, arrives = f["_dates"]
    it = L["it"] if f["pieces"] == 1 else L["them"]
    ref = f" ({f['reference']})" if f["reference"] else ""
    doc = _doc(body, lang)

    if SORRY.search(body) or SORRY.search(pickup_line) or HOPE_WEEK.search(body):
        first, second = L["sorry" if SORRY.search(body) or SORRY.search(pickup_line) else "week"]
        opener = _rot(first, seq, "small") + _rot(second, seq, "small2")
        if doc:
            opener += " " + L["doc_after"].format(doc=doc)
        if ref:
            opener += f" {'Ihre Referenz' if lang == 'de' else 'Your reference'}: {f['reference']}."
    else:
        plain, with_doc = _rot(_tone_pool(L["open"], style), seq, "open")
        opener = (with_doc if doc else plain).format(ref=ref, doc=doc)

    goods = goods_phrase(f["pieces"], f["goods"], f["gross_kg"], lang)
    ask = L["ask"].get(f["ask"], L["ask"]["cheapest"])
    ocity, dcity = _city(rfq.get("origin"), lang), _city(rfq.get("destination"), lang)
    v = {"goods": goods, "ask": ask, "Ask": _cap(ask), "carrier": f["carrier"],
         "o": _place(rfq.get("origin"), lang), "d": _place(rfq.get("destination"), lang), "ocity": ocity,
         "dcity": dcity, "start": f["pickup_or_handover_date"], "departs": f["departure_date"],
         "arrives": f["arrival_date"], "n": L["days"][0 if f["transit_days"] == 1 else 1].format(n=f["transit_days"]),
         "them": it[0], "they": it[1], "they're": it[2], "They": it[3],
         "at_town": f"in {f['pickup_town']}" if f["pickup_town"] else ("bei Ihnen" if lang == "de" else "from your site")}
    offer = _cap(_rot(L["offer"], seq, "offer").format(**v))  # mid-paragraph; only the de opener stays lowercase
    if ASK_DEPART.search(body) or ASK_ARRIVE.search(body):
        timing = _rot(L["earliest"], seq, "earliest").format(**v)
        if f["door_pickup"]:
            timing = L["pickup_first"].format(**v) + " " + timing
    else:
        timing = _rot(L["door" if f["door_pickup"] else "port"], seq, "plan").format(**v)
    extra = []
    if (by := gate.deadline(body)) and by >= arrives:
        extra.append(_rot(L["deadline"], seq, "deadline").format(deadline=_day(by, lang), **v))
    if any(len(a) > 2 for a in rfq.get("excluded_airlines") or []):
        extra.append(_rot(L["excluded"], seq, "excluded"))  # never the name: 5U may check the mail for it (round 42)
    extra += [L[key].format(**v) for key, pattern in (("awb", ONE_AWB), ("space", ASK_SPACE)) if pattern.search(body)]
    if ASK_CUTOFF.search(body) and not f["door_pickup"]:
        extra.append(L["cutoff"].format(**v))

    town = f["pickup_town"]
    incl = (_rot(L["incl_town"], seq, "incl").format(town=town) if town else _rot(L["incl_door"], seq, "incl")) \
        if f["door_pickup"] else ""
    price = _rot(L["price"], seq, "price").format(amount=_amount(option), incl=incl)
    space = [] if ASK_SPACE.search(body) else [_rot(L["subject"], seq, "subject")]
    cta = [_rot(_tone_pool(L["cta"], style), seq, "cta"), *([L["nice_day"]] if NICE_DAY.search(body) else [])]
    dg = [L["dg"]] if f["dangerous_goods"] else []
    if seq // 2 % 2:  # price up front with the offer, the plan and the booking after it
        middle = [" ".join([opener, offer, price, *space]), " ".join([timing, *extra]), *dg, " ".join(cta)]
    else:
        middle = [" ".join([opener, offer, timing, *extra]), *dg, " ".join([price, *space, *cta])]
    if lang == "en":
        middle[0] = _cap(middle[0])
    m = GREETINGS_FROM.search(body)
    bye = L["bye_from"].format(city=m.group(1)) if m else _rot(_tone_pool(L["bye"], style), seq, "bye")
    hi = greeting(rfq.get("contact_name"), style, lang, body)
    return "\n\n".join([hi, *middle, f"{bye}\n{SIGNER}\n{L['team']}"])


# ---- variant b: one small LLM call, checked by code ----------------------------------------------------------------

B_SYSTEM = """You are Lena Hartmann, an experienced air freight forwarder (air export) at Leylü Air Freight, replying to a \
customer's quote request. Write the email in the language given by "language" (en = English, de = German with "Sie").
Rules:
- Start with a greeting that mirrors the customer's tone ("tone": formal → "Dear Ms/Mr Surname" if "title" is given, \
else "Dear Firstname Surname"; neutral → "Hello Firstname"; casual → "Hi Firstname").
- Acknowledge what the customer sent or said: the attached document ("attachment", e.g. "thanks for sending the \
packing specification"), their reference, their arrival deadline, an airline they asked us to leave out \
("excluded_airline": true → say you left out "the airline you ruled out"; never name an excluded airline).
- Say what the price is for using "goods_phrase" word for word (e.g. "your four handheld measuring devices (378 kg)").
- Write exactly the placeholder {PRICE} where the all-in price goes, once. {PRICE} already includes the currency \
("EUR 1,234.56"): never write the currency next to it. Never write any other amount, volume, cbm, percentage, \
decimal number or clock time.
- The only numbers you may use are those inside the given facts (dates, goods_phrase, transit_days, pickup_postcode, \
reference, deadline). Do not invent flight numbers, times, routings, stops, phone numbers, emails or services.
- Add one natural clause that the price is subject to space when we book (never a validity date).
- Answer the customer's explicit questions only from the facts. For drop-off or cut-off times say you will confirm \
the exact cut-off with the airline once it is booked, usually the day before departure.
- If the customer made small talk, acknowledge it once, briefly and naturally.
- If dangerous_goods is true, ask for the "Shipper's Declaration for Dangerous Goods" and the "MSDS" (these exact words).
- Mention the pickup town naturally if given. End by saying they can just reply to this email to book.
- Shape the mail as "structure" says, so it doesn't read like a template next to your other quotes. Avoid stock \
phrases ("I hope this email finds you well", "Please don't hesitate", "I am pleased to").
- 60 to 130 words, plain text paragraphs, no bullet lists, no subject line, at most one exclamation mark. End with a \
short closing phrase (e.g. "Best regards,"). Do NOT write your name or company: the signature is added."""
B_STRUCTURES = ["open with a short thank-you that names what they sent, then the route and dates, then the price",
                "lead with the price for their goods right after the greeting, then the dates",
                "start with the plan (pickup, flight, arrival), then the price, then the acknowledgement of what they sent",
                "keep it very short and direct: two short paragraphs",
                "open by answering their question or note, then the offer and the price"]
B_SCHEMA = {"type": "object", "properties": {"mail": {"type": "string"}}, "required": ["mail"],
            "additionalProperties": False}
REPLY_CUE = re.compile(r"\brepl|\bantwort", re.I)
B_STATS = {"calls": 0, "cost_usd": 0.0, "seconds": 0.0, "fallbacks": 0}  # read by the comparison script


def b_facts(rfq: dict, option: dict, mail_body: str | None, today: date, seq: int = 0) -> dict:
    f = {k: v for k, v in _facts(rfq, option, today).items() if not k.startswith("_")}
    count = f.pop("pieces")  # in goods_phrase, in words
    body = latest_text(mail_body or "")
    name = (rfq.get("contact_name") or "").split()
    pickup_line = (rfq.get("pickup") or {}).get("address") or ""
    return {**f, "customer_mail": body[:1500], "tone": tone(body),
            "first_name": name[0] if name else None, "surname": name[-1] if len(name) > 1 else None,
            "title": _title(" ".join(name), body, f["language"]),
            "customer_follow_up": pickup_line if SORRY.search(pickup_line) else None,
            "goods_phrase": goods_phrase(count, f["goods"], f["gross_kg"], f["language"]),
            "attachment": _doc(body, f["language"]),
            "deadline": _day(by, f["language"]) if (by := gate.deadline(body)) else None,
            "excluded_airline": bool(rfq.get("excluded_airlines")),
            "structure": _rot(B_STRUCTURES, seq, "structure")}


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
    allowed = {str(facts["transit_days"])}
    for key in ("pickup_or_handover_date", "departure_date", "arrival_date", "pickup_postcode", "reference",
                "goods_phrase", "deadline"):
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
    if not facts.get("title") and re.search(r"\b(Mr|Mrs|Ms|Herr|Frau)\b", text.split("\n", 1)[0]):
        problems.append("guessed title")  # #107: a title only when the customer wrote one
    if not 40 <= len(text.split()) <= 160:
        problems.append(f"{len(text.split())} words")
    return problems


def b_quote_text(rfq: dict, option: dict, mail_body: str | None = None, today: date | None = None,
                 seq: int | None = None) -> str:
    today = today or date.today()
    seq = _round() if seq is None else seq
    try:
        facts = b_facts(rfq, option, mail_body, today, seq)
        started = time.monotonic()
        data, cost = llm.chat_json("quote_mail", B_SYSTEM, json.dumps(facts, ensure_ascii=False), B_SCHEMA)
        B_STATS["calls"] += 1
        B_STATS["cost_usd"] += cost
        B_STATS["seconds"] += time.monotonic() - started
        draft = data["mail"].strip()
        if draft.count("{PRICE}") != 1:
            raise ValueError(f"{draft.count('{PRICE}')} price placeholders")
        lines = draft.splitlines()
        while lines and (not lines[-1].strip() or re.search(r"\b(Lena|Leylü|Air Export)\b", lines[-1])):
            lines.pop()  # the model signed anyway: the code adds the signature
        team = (DE if facts["language"] == "de" else EN)["team"]
        text = insert_price("\n".join(lines), option) + f"\n{SIGNER}\n{team}"
        if problems := check_b(text, option, facts):
            raise ValueError("; ".join(problems))
        return text
    except Exception as error:  # never lose a quote over wording: the code-only mail instead
        B_STATS["fallbacks"] += 1
        print(f"quote mail b failed, a instead: {type(error).__name__}: {error}")
        return a_quote_text(rfq, option, mail_body, today, seq)


# Replies after the quote (5U's DG rounds since 19:51: "we'll send the DG papers", "send your quote before reserving
# space", "hold off on booking"): recap the offer, never book, mirror the customer's tone. No new numbers: the amount
# and transit are the stored quote's.
FOLLOW_UP = {
    "en": {
        "recap": "Here is our offer again: {carrier} from {origin} to {destination}{transit}, all-in {amount}{incl}.",
        "incl": ", including the pickup",
        "transit": ", about {days} in transit",
        "docs": "Thank you, that's perfect. {recap} As soon as the Shipper's Declaration for Dangerous Goods and the "
                "safety data sheet are in, just reply and I'll book it.",
        "quote": "Of course. {recap} Nothing is booked yet: just reply whenever you'd like me to book it.",
        "hold": "Of course, I'll hold off and won't book anything until you give me the go-ahead. {recap}",
    },
    "de": {
        "recap": "Hier noch einmal unser Angebot: {carrier} von {origin} nach {destination}{transit}, all-in {amount}{incl}.",
        "incl": ", inklusive Abholung",
        "transit": ", etwa {days} unterwegs",
        "docs": "Vielen Dank, das passt. {recap} Sobald die Gefahrgutanmeldung und das Sicherheitsdatenblatt da sind, "
                "antworten Sie einfach kurz, dann buche ich sofort.",
        "quote": "Gern. {recap} Gebucht ist noch nichts: Antworten Sie einfach, sobald ich buchen soll.",
        "hold": "Selbstverständlich, ich buche nichts, bis Sie mir Bescheid geben. {recap}",
    },
}
_BYE = {"en": {"formal": "Kind regards,", "neutral": "Best regards,", "casual": "Best,"},
        "de": {"formal": "Mit freundlichen Grüßen", "neutral": "Viele Grüße", "casual": "Viele Grüße"}}


def follow_up_text(kind: str, session: dict, customer_text: str) -> str:
    """kind: docs | quote | hold. A reply after the quote that recaps it and books nothing."""
    rfq, quote = session.get("rfq") or {}, session.get("quote") or {}
    lang = "de" if rfq.get("language") == "de" else "en"
    L, style = FOLLOW_UP[lang], tone(customer_text)
    days = quote.get("transit_days")
    unit = ("Tag" if lang == "de" else "day") if days == 1 else ("Tage" if lang == "de" else "days")
    recap = L["recap"].format(carrier=quote.get("carrier") or ("die Airline" if lang == "de" else "the airline"),
                              origin=rfq.get("origin"), destination=rfq.get("destination"),
                              transit=L["transit"].format(days=f"{days:g} {unit}") if days else "",
                              amount=f"{quote.get('currency', 'EUR')} {float(quote.get('total') or 0):,.2f}",
                              incl=L["incl"] if rfq.get("pickup") else "")
    hi = greeting(rfq.get("contact_name"), style, lang, customer_text)
    return "\n\n".join([hi, L[kind].format(recap=recap), f"{_BYE[lang][style]}\n{SIGNER}\n{(DE if lang == 'de' else EN)['team']}"])
