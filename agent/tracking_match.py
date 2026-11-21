"""Find the booked shipment a tracking question is about when it names no reference. No LLM, stdlib only.

5U's tracking questions describe the shipment the way the customer's RFQ did, e.g.
"Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg, ready on 2026-11-25". So each booked session is scored
on what the question repeats from its RFQ: customer, pickup postcode or origin airport, destination, weight,
ready date. All questions seen on Sat 21 Nov (#923, #1212, #1447) follow that pattern and quote no reference.
Only a clear winner counts: a wrong shipment's status is worse than asking for the booking reference.

Kill switches (env, read at start; `off` restores the behaviour before the tracking sweep):
- TRACKING_FORMATS: weights as "1.233,00 kg" / "1,233.00 kg" / lbs, dates as 25.11.2026 / 25 Nov 2026 / 11/25/2026,
  umlauts (Kaffeerösterei = kaffeeroesterei), company words inside compounds, city names for airports, dates in
  quoted mail headers ignored.
- TRACKING_FUZZY: references as people type them (bk-50nn8e8g, BK 50NN8E8G, PO 4711 = PO-0004711 = po#4711, a rate
  ID, one typo in a BK- number) matched against our booked sessions; only a unique hit counts.
- TRACKING_CUSTOMER: a question that only names the company (or signs with the contact's full name, or quotes the
  customer's address) gets that customer's booking; several bookings of that customer (up to 3) are all answered,
  never another customer's. A question that names another known customer never gets this one's booking.
"""

import os
import re
import unicodedata
from datetime import date
from email.utils import parseaddr
from functools import lru_cache

from airports import CITY, SAME_CITY, known

FORMATS = os.environ.get("TRACKING_FORMATS", "on").lower() != "off"
FUZZY = os.environ.get("TRACKING_FUZZY", "on").lower() != "off"
CUSTOMER = os.environ.get("TRACKING_CUSTOMER", "on").lower() != "off"

MIN_SCORE = 5  # e.g. destination + weight, or customer + destination + date
WEIGHTS = {"weight": 3, "customer": 2, "destination": 2, "postcode": 2, "ready_date": 2, "origin": 1}
MAX_SAME_CUSTOMER = 3  # more bookings of one customer than this and nothing that tells them apart: ask

_KG = re.compile(r"(\d{1,3}(?:[.,  ]\d{3})+|\d+(?:[.,]\d+)?)\s*(?:kg|kilo)", re.I)
_POSTCODE = re.compile(r"\b\d{4,5}\b")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ANY_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# ---- TRACKING_FORMATS ------------------------------------------------------------------------------------------------
_KG_FORMATS = re.compile(r"(\d{1,3}(?:[.,  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?)\s*"
                         r"(kgs?|kilos?|kilograms?|kilogramm|lbs?|pounds?)\b", re.I)
_LB = 0.45359237
_MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                          "dec"))} | {"mae": 3, "mrz": 3, "mai": 5, "okt": 10, "dez": 12}
# Month names only (en/de): "ready 25.11.2026" must not be read as the month "ready" plus the day 25.
_MONTH = (r"(jan(?:uary|uar)?|feb(?:ruary|ruar)?|m(?:ar|är|aer)(?:ch|z)?|apr(?:il)?|ma[yi]|jun[ei]?|jul[iy]?|"
          r"aug(?:ust)?|sep(?:t|tember)?|o[ck]t(?:ober)?|nov(?:ember)?|de[cz](?:ember)?)\b\.?")
_DATES = re.compile(
    r"\b(\d{4})-(\d{2})-(\d{2})\b"  # 2026-11-25
    r"|\b(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})\b"  # 25.11.2026 · 25/11/2026 · 11/25/2026 · 25.11.26
    r"|\b(\d{1,2})\.(\d{1,2})\.(?!\d)"  # 25.11. (no year)
    r"|\b(\d{1,2})(?:st|nd|rd|th)?\.?\s+(?:of\s+)?" + _MONTH + r"(?:,?\s+(\d{4})\b)?"  # 25 Nov 2026 · 25. November
    r"|\b" + _MONTH + r"\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4})\b)?", re.I)  # November 25, 2026 · Nov 25th
# Lines of a quoted or forwarded mail header: their date is when the mail was sent, not the shipment's ready date.
_HEADER = re.compile(r"^\s*(?:>\s*)*(?:date|sent|gesendet|datum|on\s.+\swrote|am\s.+\sschrieb)\b.*$", re.I | re.M)
_CITIES = None


@lru_cache(maxsize=2048)
def _fold(text: str) -> str:
    """Lower case, umlauts spelled out (ö = oe), other accents dropped: São Paulo = sao paulo, Rösterei = roesterei."""
    text = text.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


@lru_cache(maxsize=64)
def _words(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", _fold(text)))


def _word_hit(word: str, words: frozenset[str]) -> bool:
    """A company word as written, or as the end of a German compound for longer words (roesterei in
    kaffeeroesterei). Short words and word starts never: "auer" in "sauerland", "meyer" in "meyerhof" or
    "obermeyer" are other companies."""
    return word in words or (len(word) >= 6 and any(len(w) > len(word) and w.endswith(word) for w in words))


def is_date(text: str) -> bool:
    """`2026-11-25` looks like a reference to the reference regex; it isn't one."""
    return bool(_ISO_DATE.match(text))


def _number(raw: str) -> float:
    """1233 · 1,233 · 1.233 · 1 233 → 1233.0; 1233,5 / 1233.5 → 1233.5."""
    if re.fullmatch(r"\d{1,3}(?:[.,  ]\d{3})+", raw):
        return float(re.sub(r"[.,  ]", "", raw))
    return float(raw.replace(",", "."))


def _number_formats(raw: str) -> float:
    """Also 1.233,00 · 1,233.00 · 1 233,5 (thousands and decimals with different separators)."""
    m = re.fullmatch(r"(\d{1,3}(?:([.,  ])\d{3})+)([.,])(\d{1,2})", raw)
    if m and m[3] != m[2]:
        return float(f"{re.sub(r'[.,  ]', '', m[1])}.{m[4]}")
    return _number(raw)


def _weights_in(text: str) -> list[float]:
    if not FORMATS:
        return [_number(m.group(1)) for m in _KG.finditer(text)]
    return list(_weights_formats(text))


@lru_cache(maxsize=64)
def _weights_formats(text: str) -> tuple[float, ...]:
    found = []
    for m in _KG_FORMATS.finditer(text):
        try:
            value = _number_formats(m.group(1))
        except ValueError:  # "1.233.00": no number we can trust
            continue
        found.append(value * _LB if m.group(2).lower().startswith(("lb", "pound")) else value)
    return tuple(found)


def _dates_in(text: str, year: int | None) -> frozenset[str]:
    """ISO dates of every date the text writes (header lines of quoted mails left out). year: for "25.11." / "Nov 25"."""
    return _dates(text, year, False)


def _ready_dates_in(text: str, year: int | None) -> frozenset[str]:
    """Only the dates written as the ready or pickup date ("ready on 28.11.2026", "Abholung am 28.11.")."""
    return _dates(text, year, True)


_READY = re.compile(r"\b(?:ready|pick\s?-?up|collect\w*|available|abhol\w*|bereit\w*|versandbereit)\b[^.\n]{0,20}$", re.I)


@lru_cache(maxsize=256)
def _dates(text: str, year: int | None, ready_only: bool) -> frozenset[str]:
    found = set()
    cleaned = _HEADER.sub(" ", text)
    for m in _DATES.finditer(cleaned):
        if ready_only and not _READY.search(cleaned[max(0, m.start() - 40):m.start()]):
            continue
        g = m.groups()
        try:
            if g[0]:
                d = date(int(g[0]), int(g[1]), int(g[2]))
            elif g[3]:
                y = int(g[5]) + (2000 if len(g[5]) == 2 else 0)
                first, second = int(g[3]), int(g[4])
                d = date(y, second, first) if second <= 12 else date(y, first, second)  # day first, unless impossible
            elif g[6]:
                if year is None:
                    continue
                d = date(year, int(g[7]), int(g[6]))
            elif g[8]:
                month = _MONTHS.get(_fold(g[9])[:3])
                if not month or not (g[10] or year):
                    continue
                d = date(int(g[10] or year), month, int(g[8]))
            else:
                month = _MONTHS.get(_fold(g[11])[:3])
                if not month or not (g[13] or year):
                    continue
                d = date(int(g[13] or year), month, int(g[12]))
        except ValueError:
            continue
        found.add(d.isoformat())
    return frozenset(found)


def _cities() -> dict[str, str]:
    """City names as words (" sao paulo ") → airport code."""
    global _CITIES
    if _CITIES is None:
        _CITIES = {f" {' '.join(re.findall(r'[a-z0-9]+', _fold(name)))} ": code for name, code in CITY.items()}
    return _CITIES


@lru_cache(maxsize=64)
def airports_in(text: str) -> frozenset[str]:
    """Airport codes the text names: an upper-case code our lanes know (EWR counts as JFK) or a city name."""
    codes = {SAME_CITY.get(c, c) for c in re.findall(r"\b[A-Z]{3}\b", text)}
    codes = {c for c in codes if c in known()}
    folded = " " + " ".join(re.findall(r"[a-z0-9]+", _fold(text))) + " "
    return frozenset(codes | {code for name, code in _cities().items() if name in folded})


def _gross_kg(rfq: dict) -> float:
    return sum((p.get("count") or 1) * (p.get("weight_kg") or 0) for p in rfq.get("pieces") or [])


def _customer_words(customer: str) -> set[str]:
    """`sonnberg-roesterei@hackloop.mail` → {"sonnberg", "roesterei"}: the parts a person would also write."""
    local = customer.split("@")[0].lower()
    if FORMATS:
        local = _fold(local)
    return {w for w in re.split(r"[^a-z0-9äöüß]+", local) if len(w) >= 4}


def _rfq(session: dict) -> dict:
    return session.get("rfq") if isinstance(session.get("rfq"), dict) else {}


def _known_weights(session: dict) -> list[float]:
    # The question may quote the RFQ's gross weight or the booked weight (5U's booking record): accept either.
    rfq = _rfq(session)
    return [w for w in (_gross_kg(rfq), (session.get("booking") or {}).get("weight_kg"),
                        (session.get("quote") or {}).get("chargeable_weight_kg")) if w]


def _ready_year(rfq: dict) -> int | None:
    ready = str(rfq.get("ready_date") or "")
    return int(ready[:4]) if re.match(r"\d{4}-", ready) else None


def signals(text: str, session: dict) -> dict[str, bool]:
    """Which parts of the session's RFQ the question repeats."""
    rfq = _rfq(session)
    low = text.lower()
    words = set(re.findall(r"[a-z0-9äöüß]+", low))
    known_kg = _known_weights(session)
    address = ((rfq.get("pickup") or {}).get("address") or "")
    postcodes = set(_POSTCODE.findall(address))
    destination, origin = (rfq.get("destination") or "").lower(), (rfq.get("origin") or "").lower()
    hits = {
        "weight": any(abs(w - k) <= max(1.0, k * 0.005) for w in _weights_in(text) for k in known_kg),
        "customer": bool(_customer_words(session.get("customer") or "") & words),
        "destination": bool(destination) and destination in words,
        "postcode": bool(postcodes & set(_POSTCODE.findall(text))),
        "ready_date": bool(rfq.get("ready_date")) and str(rfq["ready_date"]) in text,
        "origin": bool(origin) and origin in words,
    }
    if FORMATS:
        folded = _words(text)
        named = airports_in(text)
        hits["customer"] = hits["customer"] or bool(_customer_words(session.get("customer") or "") & folded)
        hits["destination"] = hits["destination"] or (bool(destination) and destination.upper() in named)
        hits["origin"] = hits["origin"] or (bool(origin) and origin.upper() in named)
        hits["ready_date"] = hits["ready_date"] or (bool(rfq.get("ready_date"))
                                                    and str(rfq["ready_date"]) in _dates_in(text, _ready_year(rfq)))
    return hits


def _other_date(text: str, rfq: dict, hits: dict) -> bool:
    """The question names a date that isn't this shipment's ready date (e.g. the same customer's other shipment):
    an ISO date anywhere (as before), another format only as the ready/pickup date ("ready on 28.11.2026"), so
    "booked on 21 Nov" or a quoted mail's header date is no contradiction."""
    if not rfq.get("ready_date") or hits["ready_date"]:
        return False
    if not FORMATS:
        return bool(_ANY_ISO_DATE.search(text))
    return bool(_ANY_ISO_DATE.search(_HEADER.sub(" ", text)) or _ready_dates_in(text, _ready_year(rfq)))


def score(text: str, session: dict) -> int:
    """Points for what the question repeats; 0 when it contradicts the shipment or names no weight or date of it."""
    hits = signals(text, session)
    rfq = _rfq(session)
    other_weight = _weights_in(text) and not hits["weight"]
    if _other_date(text, rfq, hits) or other_weight or not (hits["weight"] or hits["ready_date"]):
        return 0  # e.g. the same customer's other shipment: a wrong status is worse than asking for the reference
    return sum(WEIGHTS[name] for name, hit in hits.items() if hit)


def best_match(text: str, sessions: list[dict]) -> dict | None:
    """The booked session the question describes, or None when no session clearly fits."""
    # Booked = has a booking reference (same rule as booking_agent.is_booked): a pending retry is not booked yet.
    booked = [s for s in sessions if (s.get("booking") or {}).get("booking_reference")]
    ranked = sorted(((score(text, s), s) for s in booked), key=lambda x: x[0], reverse=True)
    if CUSTOMER and ranked and ranked[0][0] >= MIN_SCORE:  # "Meyer Optik, 900 kg" never gets Meyer Industrie's 900 kg
        named = {id(s): identifies(text, s) for s in booked}
        customers = {_customer(s) for s in booked if named[id(s)]}
        ranked = [(points, s) for points, s in ranked if (named[id(s)] or not customers - {_customer(s)})
                  and not other_company(text, s)]
    if not ranked or ranked[0][0] < MIN_SCORE:
        return None
    if len(ranked) > 1 and ranked[1][0] == ranked[0][0]:
        return None  # two shipments fit equally well: don't guess
    return ranked[0][1]


# ---- TRACKING_CUSTOMER: who is asking --------------------------------------------------------------------------------
# Address words that name no company on their own ("info@", "logistics@"): a match needs one word that does.
GENERIC = {"info", "sales", "mail", "office", "team", "logistics", "logistik", "export", "import", "shipping", "cargo",
           "freight", "trade", "trading", "group", "gmbh", "buyer", "purchasing", "einkauf", "versand", "contact",
           "kontakt", "service", "support", "order", "orders", "customer", "hello", "admin", "industrie", "industries",
           "industry", "international", "global", "company", "example", "hackloop", "gmail", "outlook", "yahoo",
           "hotmail", "gmx", "online", "mail", "email", "post"}
_FREE_MAIL = re.compile(r"@(?:hackloop\.mail|gmail\.|googlemail\.|outlook\.|hotmail\.|yahoo\.|gmx\.|web\.de|t-online\.)",
                        re.I)


def _customer(session: dict) -> str:
    return (session.get("customer") or "").strip().lower()


@lru_cache(maxsize=1024)
def _identity_word_sets(customer: str) -> tuple[frozenset[str], ...]:
    """The address's local part and (for a company domain) its domain: each a set of words that names the company."""
    customer = _fold(customer or "")
    local, _, domain = customer.partition("@")
    sets = [frozenset(w for w in re.split(r"[^a-z0-9]+", local) if len(w) >= 4)]
    if domain and not _FREE_MAIL.search(customer):
        sets.append(frozenset(w for w in re.split(r"[^a-z0-9]+", domain.rsplit(".", 1)[0]) if len(w) >= 4))
    return tuple(s for s in sets if s - GENERIC)


def identifies(text: str, session: dict) -> bool:
    """The question names this session's customer: their address, all words of their company (as the address writes
    them, "Sonnberg Kaffeerösterei" for sonnberg-roesterei@), or the contact's full name ("Anna Sonnberg")."""
    customer = _customer(session)
    if customer and customer in text.lower():
        return True
    words = _words(text)
    if any(all(_word_hit(w, words) for w in ws) for ws in _identity_word_sets(customer)):
        return True
    name = re.findall(r"[a-z]+", _fold(_rfq(session).get("contact_name") or ""))
    if len(name) >= 2 and all(len(p) >= 2 for p in name):
        return bool(re.search(r"\b" + r"\W+".join(map(re.escape, name)) + r"\b", _fold(text)))
    return False


def names_someone_else(text: str, session: dict, sessions: list[dict]) -> bool:
    """The question names another of our customers and not this session's one."""
    if identifies(text, session):
        return False
    me = _customer(session)
    return any(_customer(s) != me and identifies(text, s) for s in sessions)


# "Huber GmbH", "Lindqvist MedTech AB", "Kowalski Trade Sp. z o.o.": a company named by its legal form.
_LEGAL = (r"(?:GmbH(?:\s*&\s*Co\.?\s*KG)?|AG|SE|Ltd\.?|Limited|Inc\.?|LLC|Corp\.?|S\.A\.|S\.r\.l\.|Srl|S\.p\.A\.|SpA|"
          r"B\.V\.|BV|N\.V\.|AB|Oy|A/S|ApS|Sp\.\s?z\s?o\.\s?o\.)")
_COMPANY = re.compile(r"((?:[A-ZÄÖÜ][\w&'.-]*[ \t]+){1,3})" + _LEGAL + r"(?!\w)")


_CARRIER_WORDS: set[str] = set()


def _carrier_words() -> set[str]:
    """Words of the airline and trucker names on the start-kit list: "Solace Air Cargo Ltd" is no customer."""
    if not _CARRIER_WORDS:
        import csv

        from airports import DATA
        _CARRIER_WORDS.update({"air", "cargo", "airlines", "airways", "aviation", "freight", "express", "lines"})
        try:
            with (DATA / "start-kit" / "carrier-list.csv").open(newline="") as f:
                for row in csv.DictReader(f):
                    _CARRIER_WORDS.update(re.findall(r"[a-z0-9]{3,}", _fold(row.get("name") or "")))
        except OSError:
            pass
    return _CARRIER_WORDS


@lru_cache(maxsize=64)
def _companies(text: str) -> tuple[frozenset[str], ...]:
    found = (frozenset(re.findall(r"[a-z0-9]{3,}", _fold(m.group(1)))) - GENERIC for m in _COMPANY.finditer(text))
    return tuple(words for words in found if words and not words <= _carrier_words())


def other_company(text: str, session: dict) -> bool:
    """The question names a company ("Meyerhof GmbH") and none of its words is this session's customer (address
    words or contact name): another company's shipment, even with the same weight and lane."""
    named = _companies(text)
    rfq_name = re.findall(r"[a-z]{3,}", _fold(_rfq(session).get("contact_name") or ""))
    mine = {w for ws in _identity_word_sets(_customer(session)) for w in ws} | set(rfq_name)
    if not named or not mine:
        return False
    return not any(_word_hit(w, company) or any(_word_hit(c, frozenset(mine)) for c in company)
                   for company in named for w in mine)


def contradicts(text: str, session: dict, sessions: list[dict] = ()) -> bool:
    """The question says something this shipment isn't: another weight, another date, only other airports, a
    reference of theirs that isn't this one's, or another customer's name. Used for every match that is not an exact
    reference (a typo, a company name, the thread): any doubt and we ask for the reference instead."""
    rfq = _rfq(session)
    hits = signals(text, session)
    if (_weights_in(text) and not hits["weight"]) or _other_date(text, rfq, hits):
        return True
    named = airports_in(text)
    if named and not named & {(rfq.get("origin") or "").upper(), (rfq.get("destination") or "").upper()}:
        return True
    labeled = labeled_refs(text)
    if labeled and rfq.get("customer_reference") and not any(_same_ref(t, rfq["customer_reference"], True)
                                                             for t in labeled):
        return True
    return other_company(text, session) or names_someone_else(text, session, list(sessions))


def customer_match(text: str, sessions: list[dict], everything: list[dict] | None = None) -> list[dict]:
    """The bookings of the one customer the question names, narrowed by what it says (airport, weight, date).
    [] when it names nobody, several customers, a customer with a booking still waiting for its reference, or more
    than MAX_SAME_CUSTOMER bookings it doesn't tell apart. Never another customer's booking."""
    booked = [s for s in sessions if (s.get("booking") or {}).get("booking_reference")]
    customers = {_customer(s) for s in booked if identifies(text, s)}
    if len(customers) != 1:
        return []
    [customer] = customers
    if any(_customer(s) == customer and not (s.get("booking") or {}).get("booking_reference")
           and (s.get("stage") == "booked" or (s.get("booking") or {}).get("pending_rate_id")) for s in everything or []):
        return []  # booked by email or the portal's answer got lost: the question may be about that booking
    mine = [s for s in booked if _customer(s) == customer and not contradicts(text, s, booked)]
    return mine if len(mine) <= MAX_SAME_CUSTOMER else []


# ---- TRACKING_FUZZY: references as people type them ------------------------------------------------------------------
# bk-50nn8e8g · BK 50NN8E8G · BK50NN8E8 (typo). Without a dash the number needs a digit: "BK reference" is no number.
BK_ANY = re.compile(r"\bBK([\s_./#:–—-]*)([A-Z0-9]{7,9})\b", re.I)
TEAM_REF = re.compile(r"\bS-0*(\d+)\b", re.I)
RATE_REF = re.compile(r"\bR-[A-Za-z0-9_-]{3,}", re.I)
# "PO 4711", "P.O. 4711", "po#4711", "PO-Nr. 4711", "order number is 4711", "Bestellnummer 4711", "Ihre Referenz: A-12"
_LABELED = re.compile(
    r"\b(?:p\.?\s?o\.?|purchase\s+order|order|ref(?:erence|erenz)?|bestell\w*|auftrag\w*|kommission\w*)"
    r"(?:\s*(?:no\.?|nr\.?|number|nummer|num\.?|is|ist|lautet|#|:|-|\.))*\s*#?\s*"
    r"([A-Za-z0-9][A-Za-z0-9/-]*\d[A-Za-z0-9/-]*)", re.I)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9#/-]*[A-Za-z0-9]")
_LABEL_PREFIX = re.compile(r"^(?:PO|ORDER|REF|NR|NO)(?=\d)")
_CONFUSABLE = str.maketrans({"O": "0", "I": "1", "L": "1"})


def _norm(ref: str) -> str:
    """Upper case, no separators, no leading zeros in a number: PO-0004711 = po#4711 = PO 4711 → PO4711."""
    return re.sub(r"(?<![0-9])0+(?=[0-9])", "", re.sub(r"[^A-Z0-9]", "", ref.upper()))


def _core(ref: str) -> str:
    """The reference without its label: PO-4711 → 4711."""
    return _LABEL_PREFIX.sub("", _norm(ref))


def labeled_refs(text: str) -> list[str]:
    """References after a label (PO, order, Bestellnummer, ref ...): not dates, not our own BK-/S-/R- keys."""
    return [m for m in _LABELED.findall(text) if not is_date(m) and len(_core(m)) >= 3
            and not (BK_ANY.fullmatch(m) or TEAM_REF.fullmatch(m) or RATE_REF.fullmatch(m))]


def _bk_number(m: re.Match) -> str | None:
    separator, number = m.group(1), m.group(2)
    return number.upper() if re.search(r"[-–—]", separator) or re.search(r"\d", number) else None


def _same_ref(token: str, stored: str, labeled: bool) -> bool:
    """A reference in the mail is the stored customer reference: the same characters typed with their letters (any
    case, separators, leading zeros: po#4711 = PO-0004711 for PO-4711), or the same number after a label (PO 4711).
    A bare number only counts when it is long (an SAP PO like 4500123456): a postcode or a weight is never one."""
    full, stored_full = _norm(token), _norm(stored)
    if not re.search(r"\d", stored_full):
        return False
    if full == stored_full and len(full) >= 4 and re.search(r"[A-Z]", full):
        return True
    core, stored_core = _core(token), _core(stored)
    if not stored_core or core != stored_core:
        return False
    return len(core) >= 3 if labeled else (core.isdigit() and len(core) >= 6)


def _typo(a: str, b: str) -> bool:
    """At most one wrong, missing, extra or swapped character (O/0 and I/L/1 read alike)."""
    a, b = a.upper().translate(_CONFUSABLE), b.upper().translate(_CONFUSABLE)
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1
                                  and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def bk_tokens(text: str) -> list[str]:
    """Every BK- number the text writes, upper case without the prefix (also with a typo)."""
    return [n for m in BK_ANY.finditer(text) if (n := _bk_number(m))]


def _bk(session: dict) -> str:
    return re.sub(r"^BK[^A-Z0-9]*", "", ((session.get("booking") or {}).get("booking_reference") or "").upper())


def typo_agrees(text: str, session: dict, sender: str = "", thread_session: dict | None = None) -> str:
    """What else says a BK- number with a typo means this booking ("" for nothing): 5U's trap references are one
    character off ours, so the typo alone never answers. The sender is the booking's customer (same address, or the
    same company domain; never a shared mail domain like hackloop.mail), the mail is in that customer's thread, the
    question names the customer (identifies) or repeats the shipment's weight or lane (destination plus origin or
    pickup postcode)."""
    customer = _customer(session)
    address = parseaddr(sender or "")[1].lower()
    if customer and address == customer:
        return "sender"
    domain = address.partition("@")[2]
    if domain and domain == customer.partition("@")[2] and not _FREE_MAIL.search("@" + domain):
        return "sender's domain"
    if thread_session and customer and _customer(thread_session) == customer:
        return "thread"
    if identifies(text, session):
        return "name"
    hits = signals(text, session)
    if hits["weight"]:
        return "weight"
    if hits["destination"] and (hits["origin"] or hits["postcode"]):
        return "lane"
    return ""


def reference_match(text: str, sessions: list[dict], sender: str = "",
                    thread_session: dict | None = None) -> tuple[dict | None, str]:
    """The booked session a reference in the question names, however it is typed: (session, how) or (None, "").
    Exact keys first (booking reference, our S- reference, rate ID, the customer's own reference), then a BK- number
    with one typo, only when something else agrees with that booking (typo_agrees: sender, thread, name, weight,
    lane). Only a single session counts; a typo or a customer reference that contradicts the question's other details
    (or names another customer) counts for nothing."""
    booked = [s for s in sessions if (s.get("booking") or {}).get("booking_reference")]
    tokens = bk_tokens(text)
    teams = {int(n) for n in TEAM_REF.findall(text)}
    rates = {r.lower() for r in RATE_REF.findall(text)}

    def unique(found: list[dict]) -> dict | None:
        ids = {s["id"] for s in found}
        return found[0] if len(ids) == 1 else None

    exact = [s for s in booked if _bk(s) in tokens
             or s["id"] in teams or _norm(str((s.get("booking") or {}).get("team_reference") or "x")) in {f"S{n}" for n in teams}
             or {str((s.get("booking") or {}).get("rate_id") or "").lower(),
                 str((s.get("quote") or {}).get("rate_id") or "").lower()} & rates]
    if exact:
        return (unique(exact), "reference") if unique(exact) else (None, "")
    labeled = labeled_refs(text)
    bare = [t for t in _TOKEN.findall(text) if re.search(r"\d", t) and not is_date(t)]
    own = [s for s in booked if (ref := _rfq(s).get("customer_reference"))
           and (any(_same_ref(t, str(ref), True) for t in labeled) or any(_same_ref(t, str(ref), False) for t in bare))]
    if own:
        hit = unique(own)
        return (hit, "customer reference") if hit and not names_someone_else(text, hit, booked) else (None, "")
    near = [s for s in booked if _bk(s) and any(_typo(t, _bk(s)) for t in tokens)]
    hit = unique(near)
    if hit and not contradicts(text, hit, booked) and (why := typo_agrees(text, hit, sender, thread_session)):
        return hit, f"booking reference with a typo and the {why}"
    return None, ""
