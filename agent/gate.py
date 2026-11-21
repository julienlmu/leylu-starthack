"""Quote gate: the last check before a quote leaves. Free (rules only, no LLM), runs on every quote.

Every rejected round so far was a quote a careful forwarder would have stopped: round 1 `too_low` (door-to-port
without the trucking), rounds 10 and 11 `dg_docs_missing` (dangerous goods named only in the attachment). Each new
trap so far has been "something in the request the quote must react to". The gate collects those reactions in one
place, so a new trap is one more rule here, not a patch spread over extract, pricing and templates.

review() returns findings, each with a level:
- fix:  we change the quote ourselves (pick another option, add a sentence the customer needs). Sent as usual.
- hold: a person should look. The session is flagged (ntfy push via the backend) and the quote still goes out on its
        own at GATE_AUTO_SEND_SECONDS after the RFQ, because no answer scores nothing (dead man's switch).
- note: only logged.

Added sentences never contain digits: a quote states exactly one amount (the scorer reads it).
GATE_MODE=enforce (default) | warn (log only, change nothing, never hold) | off: switch without a deploy.
"""

import os
import re
import statistics
from datetime import date, timedelta

MODE = os.environ.get("GATE_MODE", "enforce").lower()
OUTLIER_RATIO = float(os.environ.get("GATE_OUTLIER_RATIO", "0.5"))  # chosen below half the median → a part is missing
MONEY = re.compile(r"\d[\d,.]*\.\d{2}")

# ---- special cargo: what the request says → what the quote must say ------------------------------------------------
# DG beyond the words dg.py / attachments.py already catch. A hit sets rfq["dangerous_goods"], so the template's
# own DG paragraph (MSDS + DGD, 8 languages) is used: never two DG paragraphs.
DG_EXTRA = re.compile(
    r"\b(UN\s?-?\d{4}|dry\s*ice|carbon\s+dioxide,?\s+solid|radioactive|infectious\s+substances?|biological\s+substances?"
    r"|corrosive|oxidi[sz]ing|toxic\s+substances?|compressed\s+gas|gas\s+cylinders?|fireworks|safety\s+matches|"
    r"magneti[sz]ed\s+material|flash\s*point|IATA\s+DGR|hazard\s+class|packing\s+group\s+(?:I{1,3}|[123])|"
    r"Gefahrgut(?:klasse)?|matières\s+dangereuses|mercancías?\s+peligrosas?|tehlikeli\s+madde)\b", re.I)
NEGATED = re.compile(r"\b(?:non|not|no|kein\w*|nicht)[- ]?(?:dangerous|hazardous|corrosive|toxic|radioactive|"
                     r"flammable|magneti[sz]ed|Gefahrgut)\b", re.I)

# code, pattern, level, English sentence, German sentence (other languages get the English one)
SPECIAL = [
    ("temperature", re.compile(r"temperature[- ]?(?:controlled|sensitive)|cold[- ]chain|refrigerated|reefer|"
                               r"deep[- ]?frozen|\bfrozen\b|\bchilled\b|keep\s+(?:cool|cold|refrigerated)|"
                               r"\d\s*(?:-|–|to|and|bis)\s*\+?\d+\s*°\s?C\b|gekühlt|Kühlkette|Kühlware|tiefgekühlt",
                               re.I), "fix",
     "As the goods need a controlled temperature, we book them as temperature-controlled cargo: please confirm the "
     "required range and whether a data logger travels with the shipment.",
     "Da die Ware temperaturgeführt reisen muss, buchen wir sie als temperaturkontrollierte Fracht: bitte bestätigen "
     "Sie uns den nötigen Temperaturbereich und ob ein Datenlogger mitreist."),
    ("perishable", re.compile(r"perishables?|fresh\s+(?:flowers|fish|meat|fruit|produce)|seafood|cut\s+flowers|"
                              r"verderbliche?", re.I), "fix",
     "We book the shipment as perishable cargo with priority handling at both airports.",
     "Wir buchen die Sendung als verderbliche Ware mit bevorzugter Abfertigung an beiden Flughäfen."),
    ("valuables", re.compile(r"\b(?:gold\s+bars|bullion|jewell?e?ry|banknotes|precious\s+(?:metals|stones)|"
                             r"diamonds|valuables|Wertfracht|Schmuck)\b", re.I), "fix",
     "As valuable cargo the shipment gets secure handling and storage; please let us know the declared value.",
     "Als Wertfracht wird die Sendung gesichert abgefertigt und gelagert; bitte nennen Sie uns den deklarierten Wert."),
    ("non_stackable", re.compile(r"non[- ]?stackable|not\s+stackable|do\s+not\s+stack|nicht\s+stapelbar", re.I), "fix",
     "We have noted that the pieces must not be stacked and book the space accordingly.",
     "Wir haben vermerkt, dass die Packstücke nicht gestapelt werden dürfen, und buchen den Platz entsprechend."),
    ("live_animals", re.compile(r"\blive\s+(?:animals?|fish|birds|insects)|livestock|hatching\s+eggs|"
                                r"lebende\s+Tiere", re.I), "hold",
     "", ""),
    ("human_remains", re.compile(r"human\s+remains|\bcoffin\b|Leichnam", re.I), "hold", "", ""),
    ("sea_freight", re.compile(r"\b(?:sea|ocean)\s+freight|by\s+sea|\bFCL\b|\bLCL\b|Seefracht", re.I), "note", "", ""),
]
OVERSIZE = ("Some pieces are larger than lower-deck size, so they fly on a freighter's main deck: the airline confirms "
            "the space when we book.",
            "Einige Packstücke sind größer als das Unterdeck erlaubt und fliegen daher auf dem Hauptdeck eines "
            "Frachters: die Airline bestätigt den Platz bei der Buchung.")
HEAVY_PIECE_KG = 1500  # one piece above this needs a forklift slot and main-deck loading
LOWER_DECK_HEIGHT_CM, MAX_LENGTH_CM = 160, 300
INJECTION = re.compile(r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)\s+instructions|"
                       r"system\s+prompt|you\s+are\s+(?:an?\s+)?(?:AI|language\s+model|assistant)|"
                       r"disregard\s+(?:your|the)\s+(?:rules|instructions)", re.I)

# ---- constraints next to "cheapest" / "fastest" ---------------------------------------------------------------------
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                          "dec"))} | {"mär": 3, "mai": 5, "okt": 10, "dez": 12}
# DEADLINE_FORMATS=off: only the formats above (ISO, 28.11.2026, 28 November 2026, November 28, 2026; English/German).
# On: also 28/11/2026, a date without the year ("November 28", "28.11.") and Italian/Spanish/French/Dutch/Polish words.
DEADLINE_FORMATS = os.environ.get("DEADLINE_FORMATS", "on").lower() != "off"
if DEADLINE_FORMATS:
    MONTHS |= {"gen": 1, "ene": 1, "fév": 2, "fev": 2, "abr": 4, "avr": 4, "mag": 5, "giu": 6, "juil": 7, "juin": 6, "lug": 7,
               "ago": 8, "aoû": 8, "aou": 8, "set": 9, "ott": 10, "déc": 12, "dic": 12}
    _YEAR = r"(?:,?\s+\d{4})?"
    _DATE = (r"(\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{1,2}\.\d{1,2}\.(?!\d)|"
             r"\d{1,2}(?:st|nd|rd|th|er)?\.?\s+(?:of\s+)?[^\W\d_]{3,}\.?" + _YEAR + r"|"
             r"[^\W\d_]{3,}\.?\s+\d{1,2}(?:st|nd|rd|th)?\b" + _YEAR + r")")
    _OTHER = (r"|(?:entro\s+(?:e\s+non\s+oltre\s+)?(?:il\s+)?|a\s+m[aá]s\s+tardar\s+(?:el\s+)?|au\s+plus\s+tard\s+(?:le\s+)?|"
              r"uiterlijk\s+(?:op\s+)?|najp[oó][źz]niej\s+(?:do\s+)?)" + _DATE)
else:
    _DATE = (r"(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{2,4}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-zä]{3,}\.?\s+\d{4}|"
             r"[A-Za-z]{3,}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})")
    _OTHER = ""
DEADLINE = re.compile(r"(?:arrive|arrival|delivered|delivery|be\s+(?:in|at)\s+\w+|land|there|needed|need\s+it|required)"
                      r"[^.\n]{0,40}?(?:by|before|no\s+later\s+than|latest(?:\s+by)?|until|on\s+or\s+before)\s+"
                      r"(?:the\s+)?" + _DATE + r"|(?:spätestens|bis\s+(?:zum|spätestens))\s+(?:am\s+)?" + _DATE + _OTHER,
                      re.I)
BUDGET = re.compile(r"(?:budget(?:\s+is)?|max(?:imum)?|under|below|no\s+more\s+than|not\s+(?:more|above)\s+than|"
                    r"up\s+to|höchstens|maximal|unter)\s+(?:of\s+)?(?:EUR|€)\s?(\d[\d.,]*)", re.I)
# QUOTE_CURRENCY: "please quote in USD" → the quote is written in USD at the rate the portal states (backend "fx", EUR
# per 1 unit; FX_FALLBACK if the portal never stated one). Only the mail itself counts, never a packing list's "value in
# USD". off = the old hold: a person decides, the EUR quote goes out.
QUOTE_CURRENCY = os.environ.get("QUOTE_CURRENCY", "on").lower() != "off"
_CUR = (r"(USD|US[\s-]*dollars?|dollars?|CHF|Swiss\s+francs?|Schweizer\s+Franken|GBP|pounds?\s+sterling|"
        r"britischen?\s+Pfund)")
# Only an explicit request for our quote (review of #125): a request verb ("please quote in USD", "can you price this in
# USD", "send your offer in US dollars"), the quote itself ("quotation in CHF", "Angebot bitte in CHF"), or
# "prices/rates in X please". Never "item price in USD: 45" or "our offer in USD to the end client was 50k".
ASKED_CURRENCY = re.compile(
    r"(?:\b(?:please|kindly|pls|can\s+you|could\s+you|would\s+you|bitte)\s+(?:also\s+|just\s+)?(?:quote|price)\s+"
    r"(?:us\s+|it\s+|this\s+|the\s+shipment\s+)?(?:all-in\s+)?|"
    r"\b(?:send|give)\s+(?:us\s+)?(?:your|the|a)\s+(?:quote|quotation|offer)\s+|"
    r"\b(?:quotation|quote|angebot)\s+(?:please\s+|bitte\s+)?)"
    r"in\s+" + _CUR + r"\b(?!\s*[\d$€£])"  # an amount right after ("in USD 12,400"); "quote in USD: 3 pieces" asks
    r"|\b(?:prices|rates|preise)\s+in\s+" + _CUR.replace("(", "(?P<cur2>", 1) + r"\s+(?:please|bitte)\b", re.I)
# A sentence about the goods or their value, an amount, EUR named too, or a negation: never a request for the quote
# currency.
NOT_ASKED = re.compile(r"\b(?:value|invoice|customs|goods|unit|item|product|purchase|article|commodity|insurance|insured|"
                       r"declared|end\s+client|per\s+(?:piece|item|unit)|wert|warenwert|rechnung|zoll|artikel|stück|"
                       r"ware|EUR|euros?)\b|€|\b(?:not|never|don'?t|no\s+need|nicht|kein\w*)\b[^.!?\n]{0,20}"
                       r"\b(?:in\s+)?(?:USD|CHF|GBP|dollars?|francs?|franken|pfund)\b|"
                       r"\b(?:not|never)\s+(?:be\s+)?accept\w*|nicht\s+akzeptiert", re.I)


def asked_currency(text: str) -> str | None:
    """USD / CHF / GBP when the customer explicitly asks for our quote in it, else None."""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        if (m := ASKED_CURRENCY.search(sentence)) and not NOT_ASKED.search(sentence):
            return _currency(m.group(1) or m.group("cur2"))
    return None


OTHER_CURRENCY = re.compile(r"\b(?:in|price\s+in|quote\s+in|prices?\s+in|all-in\s+\w*\s*in)\s+"
                            r"(USD|US\s*dollars?|CHF|Swiss\s+francs?|GBP|pounds?\s+sterling)\b", re.I)


def _currency(word: str) -> str:
    w = word.lower()
    return "CHF" if ("chf" in w or "fran" in w) else "GBP" if ("gbp" in w or "pound" in w or "pfund" in w) else "USD"


def _finding(code: str, level: str, text: str) -> dict:
    return {"code": code, "level": level, "text": text}


def _parse_date(text: str, year: int | None = None) -> date | None:
    """A date as the customer wrote it. year: for a date without one ("November 28", "28.11.")."""
    text = text.strip().rstrip(",")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text)
        if m := re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", text):
            y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
            return date(y, int(m[2]), int(m[1]))
        if not DEADLINE_FORMATS:
            text = text.rstrip(".")
        if m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-zä]{3,})\.?\s+(\d{4})", text):
            return date(int(m[3]), MONTHS[m[2][:3].lower()], int(m[1]))
        if m := re.fullmatch(r"([A-Za-z]{3,})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", text):
            return date(int(m[3]), MONTHS[m[1][:3].lower()], int(m[2]))
        if not DEADLINE_FORMATS:
            return None
        text = text.rstrip(".") if not re.fullmatch(r"\d{1,2}\.\d{1,2}\.", text) else text
        if m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", text):  # Europe: day first, unless that can't be
            y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
            first, second = int(m[1]), int(m[2])
            return date(y, second, first) if second <= 12 else date(y, first, second)
        if year is None:
            return None
        if m := re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.", text):
            return date(year, int(m[2]), int(m[1]))
        if m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th|er)?\.?\s+(?:of\s+)?([^\W\d_]{3,})\.?(?:,?\s+(\d{4}))?", text):
            return date(int(m[3] or year), MONTHS[m[2][:3].lower()], int(m[1]))
        if m := re.fullmatch(r"([^\W\d_]{3,})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", text):
            return date(int(m[3] or year), MONTHS[m[1][:3].lower()], int(m[2]))
    except (KeyError, ValueError):
        return None
    return None


def deadline(text: str, after: date | None = None) -> date | None:
    """The latest arrival date the customer names ("must arrive by 2026-11-30", "spätestens am 30.11.2026").

    after: the ready date; a date written without a year is the first one on or after it.
    """
    for m in DEADLINE.finditer(text):
        raw = next(g for g in m.groups() if g)
        year = after.year if after else None
        found = _parse_date(raw, year)
        if found and after and year and not re.search(r"\d{4}", raw) and found < after:
            found = _parse_date(raw, year + 1)  # "by January 5" asked in November
        if found and (after is None or found > after):  # on or before the ready date: a deadline for our quote
            return found
    return None


def budget(text: str) -> float | None:
    if m := BUDGET.search(text):
        raw = m.group(1).rstrip(".,")
        if re.search(r"[.,]\d{3}$", raw) or re.search(r"[.,]\d{3}[.,]", raw):  # 3.000 / 3,000 / 3.000,00
            raw = re.sub(r"[.,](?=\d{3}\b)", "", raw)
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            return None
    return None


def _arrives(option: dict, ready: date | None) -> date | None:
    if ready is None or option.get("transit_days") is None:
        return None
    return ready + timedelta(days=-(-float(option["transit_days"]) // 1))  # whole days, rounded up


def _ready(rfq: dict) -> date | None:
    try:
        return date.fromisoformat(rfq.get("ready_date") or "")
    except ValueError:
        return None


def _pick(options: list[dict], ask: str | None) -> dict:
    """The same rule as the backend: fastest → fewest days, ties cheaper; else cheapest, ties faster."""
    slow = max((o["transit_days"] for o in options if o.get("transit_days") is not None), default=99)
    days = lambda o: o["transit_days"] if o.get("transit_days") is not None else slow  # noqa: E731
    if ask == "fastest":
        return min(options, key=lambda o: (days(o), o["total"]))
    return min(options, key=lambda o: (o["total"], days(o)))


def _same(a: dict, b: dict) -> bool:
    return all(a.get(k) == b.get(k) for k in ("source", "carrier", "rate_id", "total"))


# ---- the review ---------------------------------------------------------------------------------------------------

def review(rfq: dict, result: dict, mail: dict, texts: list[str] | tuple = (), elapsed_s: float | None = None) -> dict:
    """Checks a priced request before the quote is written.

    rfq / result: the Rfq and the /api/price response. texts: readable attachment texts (packing list, SLI).
    Returns {"chosen": option to quote, "sentences": extra sentences for the quote, "findings": [...], "hold": bool}.
    In warn mode the findings are the same, but chosen, sentences and hold are never changed.
    """
    chosen, options = result.get("chosen"), [o for o in result.get("options") or [] if o.get("total") is not None]
    out = {"chosen": chosen, "sentences": [], "findings": [], "hold": False}
    if MODE == "off" or not chosen:
        return out
    request = "\n".join([mail.get("subject") or "", mail.get("body") or "", *[t for t in texts if t]])
    clean = NEGATED.sub(" ", request)
    found = out["findings"]
    lang = ((rfq.get("language") or "en")[:2]).lower()
    say = lambda en, de: de if lang == "de" else en  # noqa: E731

    # 1. Dangerous goods the other checks don't know (dry ice, corrosive, …): the template asks for the papers.
    if not rfq.get("dangerous_goods") and (m := DG_EXTRA.search(clean)):
        rfq["dangerous_goods"], rfq["dg_declared"] = True, m.group(0)
        found.append(_finding("dangerous_goods", "fix", f"Dangerous goods ({m.group(0)}): the quote asks for the DG papers"))

    # 2. Special cargo: one sentence the customer expects, or a person for what we can't book blind.
    for code, pattern, level, en, de in SPECIAL:
        if m := pattern.search(clean):
            found.append(_finding(code, level, f"{code.replace('_', ' ')} ({m.group(0).strip()})"))
            if level == "fix":
                out["sentences"].append(say(en, de))

    # 3. Piece sizes from the request: main deck needed?
    pieces = rfq.get("pieces") or []
    tall = any((p.get("height_cm") or 0) > LOWER_DECK_HEIGHT_CM for p in pieces)
    long_ = any(max(p.get("length_cm") or 0, p.get("width_cm") or 0) > MAX_LENGTH_CM for p in pieces)
    heavy = any((p.get("weight_kg") or 0) > HEAVY_PIECE_KG for p in pieces)
    if tall or long_ or heavy:
        found.append(_finding("oversize", "fix", "Piece too tall, long or heavy for the lower deck"))
        out["sentences"].append(say(*OVERSIZE))

    # 4. Constraints next to the ask: arrival deadline and budget narrow the options before the pick.
    feasible, ready = options or [chosen], _ready(rfq)
    if (by := deadline(request, ready)) and ready:
        ok = [o for o in feasible if (_arrives(o, ready) or date.max) <= by]
        if ok:
            feasible = ok
            found.append(_finding("deadline", "note", f"Must arrive by {by}: {len(ok)} of {len(options)} options do"))
        else:
            found.append(_finding("deadline", "hold", f"Must arrive by {by}: no option arrives in time"))
    if (cap := budget(request)) is not None:
        ok = [o for o in feasible if o["total"] <= cap]
        if ok:
            feasible = ok
        else:
            found.append(_finding("budget", "note", f"Budget EUR {cap:,.2f}: no option is within it"))
    narrowed = len(feasible) < len(options or [chosen])
    pick = _pick(feasible, rfq.get("ask")) if feasible else chosen
    bids_only = all(o.get("source") == "carrier_bid" for o in options)  # the backend picks those 50/50 on purpose
    if narrowed and not _same(pick, chosen) and not any(_same(o, chosen) for o in feasible):
        found.append(_finding("constraint", "fix", f"{pick['carrier']} EUR {pick['total']:,.2f} meets the customer's "
                                                    f"constraint ({chosen['carrier']} doesn't)"))
        chosen = pick
    elif rfq.get("ask") == "fastest" and not bids_only and not _same(pick, chosen) and \
            (pick.get("transit_days") or 99) < (chosen.get("transit_days") or 99):
        found.append(_finding("ask", "fix", f"Fastest asked: {pick['carrier']} ({pick['transit_days']:g} d) is faster "
                                            f"than {chosen['carrier']}"))
        chosen = pick

    # 5. Price sanity: door-to-port must include the trucker (round 1 too_low); a far-too-cheap total misses a part.
    if rfq.get("pickup") and not chosen.get("pickup"):
        found.append(_finding("pickup_missing", "hold", "Door-to-port, but the price has no pickup leg (too_low risk)"))
    totals = [o["total"] for o in options]
    if len(totals) >= 3 and chosen["total"] < OUTLIER_RATIO * statistics.median(totals):
        found.append(_finding("too_low", "hold", f"EUR {chosen['total']:,.2f} is below {OUTLIER_RATIO:.0%} of the "
                                                 f"median EUR {statistics.median(totals):,.2f}: a part may be missing"))
    if chosen["total"] <= 0:
        found.append(_finding("zero_price", "hold", "The total is zero or negative"))

    for warning in result.get("warnings") or []:  # the backend's price guard (/api/price "warnings", PR #64)
        found.append(_finding("price_warning", "note", str(warning)))

    # 6. Currency, scope, tampering, time.
    code = asked_currency(f"{mail.get('subject') or ''}\n{mail.get('body') or ''}") if QUOTE_CURRENCY else None
    if code and (rate := (result.get("fx") or {}).get(code)) and chosen.get("currency", "EUR") == "EUR":
        eur = chosen["total"]
        chosen = {**chosen, "currency": code, "total": round(eur / float(rate), 2), "total_eur": eur,
                  "fx_eur_per_unit": float(rate)}
        found.append(_finding("currency", "fix", f"Customer asks for {code}: EUR {eur:,.2f} quoted as {code} "
                                                 f"{chosen['total']:,.2f} at {float(rate):g} EUR/{code}"))
    elif m := OTHER_CURRENCY.search(request):
        found.append(_finding("currency", "hold", f"Customer asks for a price in {m.group(1)}; we quote EUR"))
    if INJECTION.search(request):
        found.append(_finding("injection", "note", "The mail tries to give us instructions; prices still come from code"))
    if elapsed_s is not None and elapsed_s > 330:
        found.append(_finding("late", "note", f"{elapsed_s:.0f} s after the RFQ: the window closes at 360 s"))

    if MODE == "warn":
        return {**out, "chosen": result["chosen"], "sentences": [], "hold": False}
    return {**out, "chosen": chosen, "hold": any(f["level"] == "hold" for f in found)}


def finish(text: str, verdict: dict, rfq: dict) -> tuple[str, list[dict]]:
    """Puts the gate's sentences into the written quote and checks the mail itself. Returns (text, new findings)."""
    found = []
    if verdict["sentences"] and MODE != "warn":
        parts = text.split("\n\n")
        at = 2 if len(parts) > 3 else len(parts) - 1  # after the offer paragraph, before the price
        text = "\n\n".join(parts[:at] + [" ".join(verdict["sentences"])] + parts[at:])
    amounts, chosen = MONEY.findall(text), verdict["chosen"]
    if amounts != [f"{chosen['total']:,.2f}"]:
        found.append(_finding("amounts", "hold", f"The mail should state one amount, it states {amounts}"))
    if chosen.get("currency") and chosen["currency"] not in text:
        found.append(_finding("currency_missing", "hold", "The mail doesn't name the currency"))
    if rfq.get("dangerous_goods") and not re.search(r"MSDS|Dangerous Goods|Gefahrgut|DG", text):
        found.append(_finding("dg_papers", "hold", "Dangerous goods, but the mail doesn't ask for the DG papers"))
    return text, found


def summary(findings: list[dict]) -> str:
    return "; ".join(f"{f['level'].upper()} {f['text']}" for f in findings)

