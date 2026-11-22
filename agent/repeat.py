""""Same as our last order": a repeat request fills what the mail leaves out from the sender's previous request in the CRM.

Rules only, no LLM. Only fields the new mail does NOT give are taken (what it says always wins), and only from the
same sender address. Preferences come along too: excluded / required airlines, max transit, cheapest/fastest, the
offer file format, DG (a DG shipment stays DG). Nothing found → nothing changes (the usual ask / hand-over).
REPEAT_ORDER=off disables it.
"""
import os
import re
from datetime import date, datetime, timedelta, timezone

ON = os.environ.get("REPEAT_ORDER", "on").lower() != "off"

_LAST = r"(?:last|previous|prior|recent|earlier)"
_ORDER = r"(?:order|shipment|booking|request|inquiry|enquiry|rfq|quote|consignment|one|time)"
ASKS = re.compile("|".join([
    rf"\b(?:same|identical|similar)\s+(?:as|like|to)\s+(?:(?:my|our|the)\s+)?{_LAST}\s+{_ORDER}",
    rf"\b(?:just\s+)?(?:like|as)\s+(?:(?:my|our|the)\s+)?{_LAST}\s+{_ORDER}",
    rf"\b(?:repeat|re-?order|redo)\s+(?:of\s+)?(?:(?:my|our|the)\s+)?{_LAST}\s+{_ORDER}",
    r"\b(?:same|like|as)\s+(?:as\s+)?(?:before|last\s+time|usual)\b", r"\bthe\s+usual\s*(?:please|order|shipment|one)?\s*(?:[.!,]|$)",
    r"\bwie\s+(?:beim\s+)?(?:letzte[nms]?|vorige[nms]?)\s+mal\b",
    r"\bwie\s+(?:bei\s+)?(?:unsere[rnm]?|meine[rnm]?|die|der|das)\s+(?:letzte[nrms]?|vorige[nrms]?)\s+\w+",
    r"\bwie\s+(?:immer|gehabt|zuletzt)\b", r"\bgleiche\s+wie\s+(?:letzte|zuletzt)",
    r"\bcomme\s+(?:la\s+)?(?:derni[eè]re\s+fois|d'habitude|notre\s+derni[eè]re|ma\s+derni[eè]re)",
    r"\bcome\s+(?:l'ultima\s+volta|il\s+nostro\s+ultimo|al\s+solito|sempre)",
    r"\bcomo\s+(?:la\s+[uú]ltima\s+vez|(?:nuestro|mi)\s+[uú]ltimo|siempre|de\s+costumbre)",
    r"\bgeçen\s+(?:sefer|seferki|siparişimiz|siparişim)", r"\bzoals\s+(?:vorige\s+keer|de\s+vorige|gewoonlijk)",
    # R105: "same shipment as in my earlier request 'Air freight quote request: STR to MEL' sent on 2026-11-21 at 23:18"
    rf"\b(?:same|identical|similar)\s+(?:[\w-]+\s+){{0,3}}(?:as|like|to)\s+(?:(?:in|on|for|from|with)\s+)?"
    rf"(?:(?:my|our|the|that)\s+)?(?:[\w-]+\s+)?(?:{_LAST}\s+{_ORDER}|{_ORDER}\s+(?:from|of|sent|dated|on|we\s+sent)\b|"
    rf"{_ORDER}\s*[\"'“„«‚‘])",
    rf"\b(?:last|previous)\s+week'?s\s+{_ORDER}", rf"\b{_ORDER}\s+(?:from|of)\s+(?:last\s+week|yesterday)\b",
    rf"\b(?:my|our)\s+{_LAST}\s+{_ORDER}\s*(?:[\"'“„«‚‘]|\(|from|of|sent|dated|on)",
    r"\b(?:wie|gleiche\s+\w+\s+wie)\s+(?:in\s+|bei\s+)?(?:meiner|unserer|der|meinem|unserem|dem)\s+(?:\w+\s+)?"
    r"(?:anfrage|bestellung|sendung|auftrag|buchung)\s+(?:vom|von|„|\")",
    r"\b(?:frühere[nm]?|vorherige[nm]?|letzte[nm]?)\s+(?:anfrage|sendung)\s+(?:vom|von|„|\")",
]), re.I)
# REPEAT_AGAIN (default off, Orhun decides; off = as before): sessions 119, 189, 201 wrote "Could you quote the same
# shipment again? My earlier request, "Air freight quote to YYZ", was sent on … The cargo and pickup details are
# unchanged". We asked for the weight; the answer was exactly that earlier request's. On: a repeat order, quoted at once.
AGAIN_ON = os.environ.get("REPEAT_AGAIN", "off").lower() == "on"
AGAIN = re.compile("|".join([
    r"\b(?:the\s+)?same\s+(?:shipment|cargo|goods|consignment|sendung|ware)\s+(?:again|once\s+more|erneut|nochmal|noch\s+einmal)\b",
    r"\b(?:previous|earlier|last|original)\s+(?:request|order|enquiry|inquiry|rfq)\s*,?\s*(?:was\s+|is\s+)?[:\-]?\s*[\"'“„«‚‘]",
    r"\b(?:cargo|shipment|goods)(?:\s+and\s+pickup)?\s+details\s+(?:are|remain|stay)\s+(?:unchanged|the\s+same)\b",
]), re.I)

# fields of the previous rfq a repeat request inherits when the new one leaves them empty
# "Same as booking BK-12345, just three pallets": that exact booking, not the latest one (by_reference)
REFERENCE = re.compile(r"\b(?:same|identical|similar|like|as|repeat|re-?order|redo|wie|comme|come|como|zoals)\b[^.\n]{0,40}?"
                       r"\b(BK[\s_#:-]*[A-Z0-9]*\d[A-Z0-9]*|R-[A-Za-z0-9_-]{3,}|S-\d{1,6})\b", re.I)
PREFERENCES = ("excluded_airlines", "required_carriers", "max_transit_days", "offer_doc")


def asks(text: str) -> bool:
    return ON and bool(ASKS.search(text or "") or REFERENCE.search(text or "")
                       or (AGAIN_ON and AGAIN.search(text or "")))


def reference(text: str) -> str | None:
    """The booking reference or rate ID a repeat request names ("same as booking BK-12345")."""
    found = REFERENCE.search(text or "") if ON else None
    return found.group(1) if found else None


def _key(ref) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(ref or "").upper())


def by_reference(api, customer: str, session_id: int, ref: str) -> tuple[dict | None, str]:
    """(that booked session, "") or (None, why a person decides): exact hit only, this sender's only, booked only."""
    key = _key(ref)
    hits = [s for s in api.sessions() if s.get("id") != session_id and key in
            {_key((s.get("booking") or {}).get("booking_reference")), _key((s.get("booking") or {}).get("rate_id")),
             _key((s.get("quote") or {}).get("rate_id")), f"S{s.get('id')}"} - {""}]
    if not hits:
        return None, f"Repeat of {ref} asked, but no session has that reference"
    mine = [s for s in hits if _address(s.get("customer")) == _address(customer)]
    if not mine:
        return None, f"Repeat of {ref} asked, but that booking belongs to another customer"
    usable = [s for s in mine if (s.get("rfq") or {}).get("origin")]
    booked = [s for s in usable if (s.get("booking") or {}).get("booking_reference")]
    if len(booked) == 1:
        return booked[0], ""
    if not booked and len(usable) == 1 and key == f"S{usable[0].get('id')}":
        return usable[0], ""  # our own quote reference ("same as your offer S-98"): that request, booked or not
    return None, f"Repeat of {ref} asked, but it is {'ambiguous' if len(booked) > 1 else 'not booked'}"


def _address(sender: str | None) -> str:
    """"Anna Meyer <anna@meyer.de>" and "ANNA@meyer.de" are the same customer."""
    found = re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", sender or "")
    return found.group(0).lower() if found else (sender or "").strip().lower()


def previous(api, customer: str, session_id: int) -> dict | None:
    """The sender's latest earlier request that could be priced; a booked one first (that is "our last order")."""
    me = _address(customer)
    mine = [s for s in api.sessions() if s.get("id") != session_id and me and _address(s.get("customer")) == me
            and (s.get("rfq") or {}).get("origin") and (s.get("rfq") or {}).get("destination")]
    if not mine:
        return None
    booked = [s for s in mine if (s.get("booking") or {}).get("booking_reference")]
    return max(booked or mine, key=lambda s: s["id"])


# R105: the earlier request named by its subject and/or the time it was sent, not "our last order".
QUOTED = re.compile(r"[\"“„«‚‘']([^\"“”„«»‚‘’\n]{6,160}?)[\"”“»’‘']")
_NAMES = ["january jan januar janvier enero gennaio jänner", "february feb februar février fevrier febrero febbraio",
          "march mar märz maerz mars marzo", "april apr avril abril aprile", "may mai mayo maggio",
          "june jun juni juin junio giugno", "july jul juli juillet julio luglio", "august aug août aout agosto",
          "september sep sept septembre septiembre settembre", "october oct okt oktober octobre octubre ottobre",
          "november nov novembre noviembre", "december dec dez dezember décembre decembre diciembre dicembre"]
_MONTHS = {word: n + 1 for n, names in enumerate(_NAMES) for word in names.split()}
ISO_DAY = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
EU_DAY = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](20\d\d|\d\d)?(?!\d)")
DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th|\.)?\s+(?:of\s+)?([A-Za-zäéûÄ]{3,10})\.?(?:\s+(20\d\d))?\b")
MONTH_DAY = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(20\d\d))?\b")
CLOCK = re.compile(r"\b([01]?\d|2[0-3])[:h]([0-5]\d)\b(?!\s*(?:kg|cbm|m3|cm|%))", re.I)
YESTERDAY = re.compile(r"\b(?:yesterday|gestern|hier|ayer|ieri|dün|gisteren)\b", re.I)
LAST_WEEK = re.compile(r"\b(?:last|previous)\s+week|\bletzte[nr]?\s+woche|\bsemaine\s+derni[eè]re|"
                       r"\bla\s+semana\s+pasada|\bsettimana\s+scorsa|\bgeçen\s+hafta|\bvorige\s+week", re.I)
LANE = re.compile(r"\b([A-Z]{3})\s*(?:-|–|→|>|to|nach|à|a|naar|para)\s*([A-Z]{3})\b")
_DAYS = ["monday montag lundi lunes lunedì lunedi pazartesi maandag",
         "tuesday tues dienstag mardi martes martedì martedi salı dinsdag",
         "wednesday mittwoch mercredi miércoles miercoles mercoledì mercoledi çarşamba woensdag",
         "thursday thur thurs donnerstag jeudi jueves giovedì giovedi perşembe donderdag",
         "friday freitag vendredi viernes venerdì venerdi vrijdag",
         "saturday samstag samedi sábado sabado sabato cumartesi zaterdag",
         "sunday sonntag dimanche domingo domenica zondag"]
_WEEKDAYS = {word: n for n, names in enumerate(_DAYS) for word in names.split()}
_WEEKDAY = r"\b(?:" + "|".join(sorted(_WEEKDAYS, key=len, reverse=True)) + r")\b"
WEEKDAY = re.compile(_WEEKDAY, re.I)
# "14:30 CET": the customer's clock; a time without a zone may be any of OFFSETS hours off our UTC received_at
ZONES = {"utc": 0, "gmt": 0, "wet": 0, "bst": 1, "cet": 1, "mez": 1, "cest": 2, "mesz": 2, "eet": 2, "eest": 3,
         "est": -5, "edt": -4, "pst": -8, "pdt": -7, "sgt": 8, "hkt": 8, "jst": 9}
ZONE = re.compile(r"\b(?:(utc|gmt)\s*([+-]\s*\d{1,2})(?::?00)?|(" + "|".join(ZONES) + r"))\b", re.I)
OFFSETS = range(-10, 13)  # shortcut: whole hours Americas..Asia, no half-hour zones (India): add them if needed
WINDOW = 180  # characters after "same as my earlier request" that describe that request
_A_DATE = r"(?:" + _WEEKDAY + r"|20\d\d-\d\d-\d\d|\d{1,2}[./]\d{1,2}(?:[./](?:20)?\d\d)?|\d{1,2}(?:st|nd|rd|th|\.)?\s+[A-Za-zäé]{3,10}|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?)"
NEW_DATES = re.compile(rf"\b(?:ready|available|pick[- ]?up|collection|deliver\w*|arriv\w*|due|by|until|before|depart\w*|"
                       rf"bereit|abholbereit|abholung|lieferung|prêt|disponible|pronto|listo)\b[^.\n\d]{{0,25}}{_A_DATE}", re.I)
NEAR_S = 30 * 60  # "sent at 23:18 UTC": our received_at within half an hour


def _subject_key(text) -> str:
    text = re.sub(r"^\s*(?:(?:re|fw|fwd|aw|wg|tr|sv)\s*:\s*)+", "", str(text or ""), flags=re.I)
    return re.sub(r"[^a-z0-9äöüß]+", " ", text.lower()).strip()


def _when(iso) -> "datetime | None":
    try:
        when = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _day(text: str, today: date) -> date | None:
    """The calendar day a mail names for the earlier request (ISO, 21.11.2026, 21 Nov, Nov 21st, yesterday)."""
    if m := ISO_DAY.search(text):
        return _safe(int(m[1]), int(m[2]), int(m[3]))
    for m in [*DAY_MONTH.finditer(text), *((m[2], m[1], m[3]) for m in MONTH_DAY.finditer(text))]:
        day_, word, year = (m[1], m[2], m[3]) if isinstance(m, re.Match) else m
        month = _MONTHS.get(word.lower())
        if month and (found := _safe(int(year or today.year), month, int(day_))):
            return found
    for m in EU_DAY.finditer(text):
        if m[3] or "." in m[0]:
            year = int(m[3]) + (2000 if m[3] and len(m[3]) == 2 else 0) if m[3] else today.year
            if found := _safe(year, int(m[2]), int(m[1])):
                return found
    if YESTERDAY.search(text):
        return today - timedelta(days=1)
    if m := WEEKDAY.search(text):  # "Tuesday": the last Tuesday before today
        return today - timedelta(days=(today.weekday() - _WEEKDAYS[m[0].lower()] - 1) % 7 + 1)
    return None


def _safe(year: int, month: int, day_: int) -> date | None:
    try:
        return date(year, month, day_)
    except ValueError:
        return None


def hints(text: str, now_iso=None) -> dict:
    """What the mail says about the earlier request: {subject, lane, day, clock, last_week}; empty = 'the last one'."""
    text = text or ""
    today = (_when(now_iso) or datetime.now(timezone.utc)).date()
    if not AGAIN_ON:
        if asked := ASKS.search(text):  # only what the sentence about the earlier request says, never the new ready date
            tail = text[asked.end():asked.end() + WINDOW]
            text = text[asked.start():asked.end()] + tail.split("\n\n")[0]
    elif asked := sorted([*ASKS.finditer(text), *AGAIN.finditer(text)], key=lambda m: m.start()):
        # REPEAT_AGAIN: every such sentence (session 201: "same shipment again" first, the subject and time one paragraph on)
        spans = []
        for m in asked:
            end = m.end() + len(text[m.end():m.end() + WINDOW].split("\n\n")[0])
            if spans and m.start() <= spans[-1][1]:
                spans[-1][1] = max(spans[-1][1], end)
            else:
                spans.append([m.start(), end])
        text = " ".join(text[a:b] for a, b in spans)
    text = NEW_DATES.sub(" ", text)
    found = {}
    if quoted := [q.strip() for q in QUOTED.findall(text) if len(_subject_key(q)) >= 6]:
        found["subjects"] = quoted
    if lanes := LANE.findall(" ".join(quoted)) if quoted else []:
        found["lane"] = lanes[0]
    if day_ := _day(QUOTED.sub(" ", text), today):
        found["day"] = day_
    if clock := CLOCK.search(QUOTED.sub(" ", ISO_DAY.sub(" ", text))):
        found["clock"] = (int(clock[1]), int(clock[2]))
    if zone := ZONE.search(QUOTED.sub(" ", text)):
        found["zone"] = int(zone[2].replace(" ", "")) if zone[2] else ZONES[(zone[1] or zone[3]).lower()]
    if LAST_WEEK.search(text):
        found["last_week"] = today
    return found


def earlier(api, customer: str, session_id: int, text: str, now_iso=None) -> tuple[dict | None, str]:
    """The sender's earlier request the mail names by subject, lane in the subject, day and/or time (R105).
    (session, "") or (None, why). Quoted-only and booked sessions both count; no hint at all → previous()."""
    found = hints(text, now_iso)
    me = _address(customer)
    mine = [s for s in api.sessions() if s.get("id") != session_id and me and _address(s.get("customer")) == me
            and (s.get("rfq") or {}).get("origin") and (s.get("rfq") or {}).get("destination")]
    if not mine:
        return None, ""  # nothing to repeat: the RFQ agent says so and asks for what is missing
    if not {"subjects", "lane", "day", "clock"} & set(found):
        return previous(api, customer, session_id), ""
    pool = mine
    if found.get("subjects"):
        keys = [_subject_key(q) for q in found["subjects"]]
        by_subject = [s for s in pool if (subject := _subject_key(_subject(api, s)))
                      and any(k == subject or (min(len(k), len(subject)) >= 12 and (k in subject or subject in k))
                              for k in keys)]
        if not by_subject and found.get("lane"):  # the subject was retyped: its lane "STR to MEL" still tells
            o, d = found["lane"]
            by_subject = [s for s in pool if ((s.get("rfq") or {}).get("origin"), (s.get("rfq") or {}).get("destination"))
                          == (o, d)]
        if by_subject:
            pool = by_subject
        elif not found.get("day"):
            return None, f"Repeat of the request {found['subjects'][0]!r} asked, but no request of this sender has it"
    day_, clock = found.get("day"), found.get("clock")
    if day_ or clock:  # the customer's day/clock vs our UTC received_at: the zone named, else UTC, else any offset
        def gap(s, offset):  # seconds between that request and the day/time named, seen at that UTC offset
            w = _when(s.get("received_at"))
            if not w:
                return None
            local = (w + timedelta(hours=offset)).replace(tzinfo=None)
            if day_ and clock:
                return abs((local - datetime(day_.year, day_.month, day_.day, *clock)).total_seconds())
            if day_:
                return 0 if local.date() == day_ else None
            minutes = abs(local.hour * 60 + local.minute - clock[0] * 60 - clock[1])
            return min(minutes, 1440 - minutes) * 60
        def near(s, offsets):
            gaps = [g for o in offsets if (g := gap(s, o)) is not None and g <= NEAR_S]
            return min(gaps) if gaps else None
        # no zone named: UTC first, then the nearest offsets (Europe before the Americas or Asia)
        tiers = [[found["zone"]]] if "zone" in found else [[o for o in OFFSETS if abs(o) == n] for n in range(13)]
        for offsets in tiers:
            if hits := [(g, s) for s in pool if (g := near(s, offsets)) is not None]:
                best = min(g for g, _ in hits)  # two requests half an hour apart: the one nearer the time named
                pool = [s for g, s in hits if g == best] if clock else [s for _, s in hits]
                break
        else:
            when = " ".join(x for x in [day_ and day_.isoformat(), clock and "%02d:%02d" % clock] if x)
            return None, f"Repeat of a request from {when} asked, but this sender sent none then"
    if len(pool) > 1:  # the mail named one request: never the latest or the booked one as a guess
        return None, (f"Repeat of an earlier request asked, but {len(pool)} requests of this sender match "
                      f"({', '.join('#%s' % s['id'] for s in pool)}): a person decides")
    return pool[0], ""


def _subject(api, session: dict) -> str:
    """The subject of the session's first incoming mail (mail_in event); the session may carry it too."""
    if session.get("subject"):
        return session["subject"]
    try:
        events = api.events(session["id"]) if hasattr(api, "events") and callable(api.events) else []
    except Exception:
        return ""
    for event in events or []:
        if event.get("kind") == "mail_in":
            data = event.get("data") or {}
            if data.get("subject"):
                return data["subject"]
            if ": " in (event.get("text") or ""):
                return event["text"].split(": ", 1)[1]
    return ""


def _has_weight(rfq: dict) -> bool:
    return any(p.get("weight_kg") for p in rfq.get("pieces") or [])


def fill(rfq: dict, missing: list[str], raw: dict | None, old: dict) -> tuple[list[str], list[str]]:
    """Fills `rfq` in place from `old`; returns (missing left, what was taken)."""
    taken = []
    for field in ("origin", "destination"):
        if not rfq.get(field) and old.get(field):
            rfq[field] = old[field]
            taken.append(f"{field} {old[field]}")
    if not rfq.get("pickup") and old.get("pickup") and (taken and "origin" in taken[0] or rfq.get("origin") == old.get("origin")
                                                          and not _has_weight(rfq)):
        rfq["pickup"] = old["pickup"]  # the old origin was a pickup zone's airport: the truck leg comes with it
        taken.append("pickup")  # R105 "same shipment" from the same airport: picked up where it was before
    new = sum(p.get("count") or 0 for p in rfq.get("pieces") or [])
    was = sum(p.get("count") or 0 for p in old.get("pieces") or [])
    if not _has_weight(rfq) and _has_weight(old) and new > 1 and new != was:
        # "just three pallets this time": the new count wins, each piece as before (one old line only, else ask)
        if len(old["pieces"]) == 1:
            rfq["pieces"] = [{**old["pieces"][0], "count": new}]
            taken.append(f"pieces/weight ({new} pieces like before)")
            if not rfq.get("volume_m3") and old.get("volume_m3"):
                rfq["volume_m3"] = round(old["volume_m3"] * new / was, 3)
    elif not _has_weight(rfq) and _has_weight(old):  # shortcut: a count of 1 can't be told from "not said"
        rfq["pieces"] = [dict(p) for p in old["pieces"]]
        taken.append("pieces/weight")
        if not rfq.get("volume_m3") and old.get("volume_m3"):
            rfq["volume_m3"] = old["volume_m3"]
    if not rfq.get("commodity") and old.get("commodity"):
        rfq["commodity"] = old["commodity"]
        taken.append("commodity")
    if old.get("dangerous_goods") and not rfq.get("dangerous_goods") and any(t.startswith("pieces/weight") for t in taken):
        rfq["dangerous_goods"], rfq["dg_declared"] = True, old.get("dg_declared") or True  # same goods: still DG
        taken.append("dangerous goods")
    if (raw or {}).get("ask") is None and old.get("ask") and old["ask"] != rfq.get("ask"):
        rfq["ask"] = old["ask"]
        taken.append(f"ask {old['ask']}")
    for field in PREFERENCES:
        if not rfq.get(field) and old.get(field):
            rfq[field] = old[field]
            taken.append(field.replace("_", " "))
    filled = {"origin": bool(rfq.get("origin")), "destination": bool(rfq.get("destination")),
              "weight": _has_weight(rfq),
              "dimensions or volume": bool(rfq.get("volume_m3")) or any(p.get("length_cm") for p in rfq.get("pieces") or [])}
    return [m for m in missing if not filled.get(m)], taken
