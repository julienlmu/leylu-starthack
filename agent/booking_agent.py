"""Booking agent: a customer reply to our quote → accept / decline / question → book by rate ID and confirm.

Also records the airline's "Booking BK-… confirmed" mail and tells the customer.
"""

import os
import unicodedata
from email.utils import parseaddr
import re
import time
import threading

import amendments
import llm
import quote_style
from backend import now
from carriers import load_carriers
from inbox import latest_text, mail_data, reply_data
from rfq_agent import hand_over, sent_at
from router import CONFIRMED
from humanizer import follow_up_text
from templates import booking_confirmed_text, booking_text, confirm_text, docs_ack_text, reprice_text, tracking_text

ACCEPT = re.compile(r"\b(accept\w*|book\w*|go ahead|proceed|confirm\w*|agreed|deal|ok|okay|yes|einverstanden|buchen|"
                    r"bestätig\w*|d'accord|réserve\w*|acepto|reserv\w*|rezerw\w*|akceptuj\w*|zgoda)\b", re.I)
# After a booking, only a plain thank-you needs no person: "please cancel" or "change the date" must still reach one.
THANKS = re.compile(r"\b(thank\w*|thx|cheers|dank\w*|merci|gracias|grazie|obrigad\w*|dzięk\w*|bedank\w*)\b", re.I)
DECLINE = re.compile(r"\b(no|not|don't|decline\w*|cancel\w*|expensive|nicht|kein\w*|teuer|absage\w*|pas|annule\w*|"
                     r"caro|nie)\b", re.I)
# "OK, book it, but change the pickup to the 30th": a yes with a change is not a plain yes, it needs a person.
CHANGE = re.compile(r"\b(but|however|instead|change\w*|chang\w*|different|update\w*|correct\w*|amend\w*|"
                    r"reschedul\w*|postpone\w*|aber|jedoch|stattdessen|ändern|geändert|änderung|verschieb\w*|"
                    r"mais|pero|ma)\b", re.I)
# "OK, if you can do it 10% cheaper we will book": a yes on a condition is no yes. Never booked, a person decides.
CONDITION = re.compile(r"\b(if you (?:can|could)|provided|as long as|on condition|cheaper|discount|lower (?:the )?price|"
                       r"fewer|günstiger|billiger|rabatt|sofern|unter der bedingung|pod warunkiem|taniej|zniżk\w*|"
                       r"moins cher|remise|más barato|descuento|più economico|sconto)\b|\d\s?%", re.I)
# "nie mamy zastrzeżeń" (Polish: we have no objections) is a yes, not the decline word "nie"
NO_OBJECTION = re.compile(r"\b(nie mamy zastrzeżeń|no objections?|keine einwände|keine bedenken)\b", re.I)
NEGATED_ACCEPT = re.compile(r"\b(?:will not|won't|wont|do not|don't|cannot|can't|not able to|unable to|not|nicht)"
                            r"\s+(?:(?!wait\b|hesitate\b)\w+\s+){0,2}?(?:go ahead|proceed|book\w*|accept\w*|buchen|annehmen)\b",
                            re.I)  # "can't wait to book" / "don't hesitate to book" are a yes
# R39: "Thank you, good point. We will send you the dangerous goods documents shortly." is no yes and no question:
# we answer it ourselves (thanks, ready to book on their word) instead of handing it to a person. DOCS_ACK=off: off.
DOCS_ACK = os.environ.get("DOCS_ACK", "on").lower() != "off"
DOCS_PROMISE_WORDS = re.compile(r"\b(document\w*|declaration|safety data sheet|msds|sds|dgd|papers?|paperwork|"
                                r"unterlagen|dokument\w*|sicherheitsdatenbl\w+|erklärung)\b", re.I)
DOCS_PROMISE = re.compile(
    # R63 "We’ll send you the dangerous goods documents shortly"; the verb alone ("I'll forward your offer") is no promise
    r"(?:(?:\bwill|['’]ll)\s+(?:send|forward|provide)\b|\b(?:send (?:you |them |it )?(?:shortly|soon|later|today|"
    r"tomorrow)|attached|attach\w*|follow\w* (?:shortly|soon)|on (?:its|their) way|schicken|senden|nachreichen|anbei)\b)"
    r"[^?]{0,160}?\b(document\w*|declaration|safety data sheet|msds|sds|dgd|papers?|paperwork|unterlagen|"
    r"dokument\w*|sicherheitsdatenbl\w+|erklärung)\b|"
    r"\b(document\w*|declaration|safety data sheet|msds|sds|dgd|papers?|paperwork|unterlagen|dokument\w*)\b"
    r"[^?]{0,80}?\b(will follow|follow\w* (?:shortly|soon)|(?:are|is) attached|on (?:its|their) way|kommen)\b", re.I)


# 5U's DG follow-ups (rounds 39-41): the customer asks for the quote again, or will get back to us.
QUOTE_AGAIN = re.compile(r"\b(?:send|resend|share|repeat|forward|confirm|give)\b[^.?!]{0,40}\b(?:quote|quotation|offer|"
                         r"price|angebot)\b|\b(?:quote|offer|price|angebot)\b[^.?!]{0,20}\b(?:again|nochmal|noch einmal)\b",
                         re.I)
# A request for a *different* quote is a change for a person, never a recap of the old one: "revised quote for
# 3 pallets instead of 2", "quote again but for delivery to Munich", "price without the pickup".
QUOTE_CHANGE = re.compile(r"\b(?:revis\w*|new|updated?\s+(?:quote|price|offer)|instead|different|other|without|excluding|"
                          r"only|but|except|change\w*|amend\w*|adjust\w*|cheaper|lower|discount|deliver\w*\s+to|delivery|"
                          r"door|incoterms?|ddp|dap|exw|for\s+\d|\d+\s*(?:pallets?|pieces?|pcs|cartons?|crates?|kg|cbm|m3|tons?)|"
                          r"statt|ohne|neu\w*|ander\w*|nur|günstiger)\b", re.I)
WILL_GET_BACK = re.compile(r"\b(?:get back to you|come back to you|let you know|will check|i'?ll check|i will check|"
                           r"melde mich|gebe .{0,15}bescheid|komme .{0,20}zurück)\b", re.I)


# R39: "Please hold off on booking for now." was read as a yes ("booking") and booked. A hold is never a yes.
HOLD = re.compile(r"\b(hold off|hold on|on hold|not yet|don'?t book|do not book|"
                  r"wait (?:before|with) (?:the )?booking|before (?:we|you) book|noch nicht|nicht buchen)\b|"
                  r"\b(?:not|n't)\b[^.!\n]{0,25}\byet\b", re.I)
# "I'll check ... and get back to you": they decide later. We wait (the quote stays open), no person needed.
LATER = re.compile(r"\b(get back to you|come back to you|revert|let you know|check (?:on|with|internally)|"
                   r"melde\w* mich|komme\w* zurück|r(?:ü|ue)ckmeld\w*)\b", re.I)
# R39/R40: the documents a DG quote waited for arrive ("please find attached the shipper's declaration")
DOCS_SENT = re.compile(r"\b(attached|enclosed|please find|here (?:are|is)|anbei|im anhang|beigefügt)\b", re.I)
DOCS_BOOK = os.environ.get("DOCS_BOOK", "on").lower() != "off"
# R60: "could you please confirm that your offer covers 11 pieces …?" is answered from our data (before HOLD)
CONFIRM_ANSWERS = os.environ.get("CONFIRM_ANSWERS", "on").lower() != "off"
# Review: only a confirm-question about what we already quoted (its pieces/weight) gets "yes"; customs, insurance,
# delivery dates, transit, validity, receipts or a "not X" correction go the usual way (never a false promise).
OTHER_TOPIC = re.compile(r"\b(includ\w*|customs|clearance|insur\w*|deliver\w*|arriv\w*|transit|valid\w*|receipt|"
                         r"received|not|nicht|instead|statt|by \d|until|bis zum|zoll|versicher\w*)\b", re.I)
CONFIRM_PCS = re.compile(r"\b(\d{1,4})\s*(?:pieces?|pcs|packages?|cartons?|pallets?|colli|crates?|boxes)\b", re.I)
CONFIRM_KG = re.compile(r"\b(\d[\d.,]*)\s*(?:kg|kgs)\b", re.I)


def confirms_our_data(text: str, rfq: dict) -> bool:
    """The question names our pieces and/or weight and nothing else to promise (R60: '11 pieces … 1,674 kg … to BOM')."""
    if OTHER_TOPIC.search(text):
        return False
    count = sum(int(p.get("count") or 0) for p in rfq.get("pieces") or [])
    kg = sum(float(p.get("count") or 0) * float(p.get("weight_kg") or 0) for p in rfq.get("pieces") or [])
    pcs = [int(m) for m in CONFIRM_PCS.findall(text)]
    kgs = [float(m.replace(",", "")) if m.count(",") and "." not in m else float(m.replace(".", "").replace(",", "."))
           if "," in m else float(m) for m in CONFIRM_KG.findall(text)]
    if not pcs and not kgs:
        return False
    return all(n == count for n in pcs) and all(kg and abs(k - kg) <= 0.01 * kg for k in kgs)
CONFIRM_Q = re.compile(r"\b(?:could|can|would) you (?:please |kindly )?(?:also )?confirm\b|\bplease (?:also )?confirm\b|"
                       r"\bconfirm (?:that )?(?:your|the|this) (?:offer|quote|quotation|price|rate)\b|"
                       r"\bbitte (?:um )?best[äa]tig\w*|k[öo]nnen sie (?:bitte )?best[äa]tigen", re.I)
# A question on an open quote that the stored quote answers (the price again, dates, transit, what's included) gets
# that quote restated instead of a person; anything else (a change, a discount, customs, ...) still goes to a person.
# At most AUTO_ANSWERS per session, so two agents can't loop. QUOTE_ANSWERS=off: off.
QUOTE_ANSWERS = os.environ.get("QUOTE_ANSWERS", "on").lower() != "off"
# Review: "revised quote for 3 pallets instead of 2", "price without the pickup", "express as well", "valid until
# Friday?" are change requests: a person, never the old quote again.
NOT_PLAIN_QUOTE = re.compile(r"\b(revis\w*|new|updated?|instead|without|but|as well|also|valid\w*|express|other|"
                             r"another|more|less|fewer|different|neu\w*|ohne|auch|statt|gültig)\b", re.I)
THANKS_UPDATE = re.compile(r"\bthanks?(?: you)? for (?:the|your) update\b", re.I)  # R41: not a change request
AUTO_ANSWERS = 2
TOPIC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["topic"],
    "properties": {"topic": {"type": "string", "enum": ["quote_again", "dates", "transit", "included", "other"]}},
}
TOPIC_PROMPT = ("A customer replied to our air freight quote. What do they ask for? quote_again: the quote or price "
                "again; dates: pickup, departure or arrival dates; transit: transit time; included: what the all-in "
                "price includes; other: anything else (changes, discounts, customs, insurance, documents, ...).")


# "Where is our shipment now?" in the booked quote thread (instead of tracking@) is answered from the CRM like a
# tracking question, not handed to a person. Only a plain status question: a change, a cancellation, an invoice or a
# second question still goes to a person. TRACKING_IN_THREAD=off: a person answers it (as before).
TRACKING_IN_THREAD = os.environ.get("TRACKING_IN_THREAD", "on").lower() != "off"
STATUS_QUESTION = re.compile(
    r"\b(where is|where's|where are|status|track(?:ing)?|any (?:news|updates?)|updates? on|"
    r"has it (?:left|shipped|departed|arrived|landed|been picked up)|did it (?:leave|ship|depart|arrive|land)|"
    r"wo ist|wo sind|wo befindet|wo bleibt|sendungsstatus|stand der (?:sendung|lieferung|dinge)|"
    r"gibt es (?:etwas )?neues|schon (?:abgeholt|unterwegs|angekommen|losgeflogen))\b", re.I)
NOT_STATUS = re.compile(r"\b(invoice\w*|rechnung\w*|pay\w*|zahlung\w*|customs|zoll\w*|insurance|versicher\w*|"
                        r"document\w*|dokument\w*|price\w*|preis\w*|cost\w*|kosten|cancel\w*|storn\w*|annul\w*)\b", re.I)
UPDATE_ASK = re.compile(r"\b(?:any|an|status)\s+updates?\b|\bupdates?\s+on\b", re.I)  # "any update on it?" asks, changes nothing


def is_status_question(text: str) -> bool:
    return bool(STATUS_QUESTION.search(text)) and text.count("?") <= 1 and not NOT_STATUS.search(text) \
        and not CHANGE.search(UPDATE_ASK.sub(" ", text)) and not CONDITION.search(text)


INTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent"],
    "properties": {"intent": {"type": "string", "enum": ["accept", "decline", "question", "other"]}},
}


QUOTES = str.maketrans({"’": "'", "‘": "'", "‚": "'", "´": "'", "`": "'", "“": '"', "”": '"', "„": '"'})


def _plain(text: str) -> str:
    """R61/R63: "We’ll send", "don’t book": curly quotes and full-width forms as ASCII before any intent rule."""
    return unicodedata.normalize("NFKC", text or "").translate(QUOTES)


def is_booked(session: dict) -> bool:
    """Booked = the portal gave a booking reference. After a failed fresh booking the backend keeps
    {pending_rate_id} in `booking` so a retry books that same rate: that session is NOT booked yet."""
    return bool((session.get("booking") or {}).get("booking_reference"))


_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


def _session_lock(session_id: int) -> threading.Lock:
    """One lock per session: two "yes" mails picked up in the same poll must not both book."""
    with _locks_guard:
        return _locks.setdefault(session_id, threading.Lock())


def read_intent(body: str) -> tuple[str, float]:
    """Clear yes / clear no by rules (free); anything mixed, unclear or asking something costs one tiny LLM call."""
    text = _plain(latest_text(body))
    # "we will not go ahead with it" / "won't book": a negated yes is a no, not a mixed reply (5U's rejection notices)
    if HOLD.search(text):  # "please hold off" / "do not book yet": wait, never a yes and never a no (quote stays open)
        return "wait", 0.0
    refused = NEGATED_ACCEPT.search(text)
    yes = bool(ACCEPT.search(NEGATED_ACCEPT.sub(" ", text)))
    no = bool(refused or DECLINE.search(NO_OBJECTION.sub(" ", text)))
    changed = bool(CHANGE.search(text) or CONDITION.search(text) or HOLD.search(text))
    if yes and not no and "?" not in text and not changed:  # "ok, but can you do it cheaper?" must not book
        return "accept", 0.0
    if no and not yes:
        return "decline", 0.0
    if not yes and (WILL_GET_BACK.search(text) or DOCS_PROMISE.search(text)):
        return "other", 0.0  # "I'll check and get back to you" / "we'll send the papers": never a yes, no LLM needed
    data, cost = llm.chat_json("intent", "Does the customer accept our freight quote, decline it, or ask a question?",
                               text, INTENT_SCHEMA)
    # "Yes, but 2 pallets fewer" / "OK if 10% cheaper": never booked as quoted, even when the model calls it a yes
    return ("question" if changed and data["intent"] == "accept" else data["intent"]), cost


EMAIL_BOOKING = os.environ.get("EMAIL_BOOKING", "on") != "off"
# Waiting for the airline's "Booking BK-… confirmed" is no job for a person (R45, R46 confirmed within a minute).
EMAIL_WAIT_QUIET = os.environ.get("EMAIL_WAIT_QUIET", "on") != "off"  # off: a failed portal booking goes to a person again
# The only failure that means "the portal can't book this at all" (backend/booking.py: no portal rate ID and the airline
# isn't on the portal for the lane). A 502 from a timeout or an unreachable portal may have booked: never mail then.
EMAIL_ONLY = "book it by email with the airline"
_airlines: dict[str, str] = {}


def airline_email(name: str | None) -> str | None:
    """The carrier list's address for an airline name ("Meridian Freightways" → meridian-freightways@…)."""
    if not _airlines:
        _airlines.update({c["name"].lower(): c["email"] for c in load_carriers() if c.get("kind") == "airline"})
    return _airlines.get((name or "").strip().lower())


def price_changed(error: Exception) -> dict | None:
    """The backend's 409 {"status": "price_changed", rate_id, old_total, new_total, currency}: not booked, ask again."""
    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) != 409:
        return None
    try:
        detail = response.json().get("detail")
    except ValueError:
        return None
    return detail if isinstance(detail, dict) and detail.get("status") == "price_changed" else None


def ask_again_at_new_price(mail: dict, box, api, session: dict, change: dict) -> None:
    """R48, R49: the new price goes on the quote (so the customer's next yes books exactly that rate) and one short
    mail asks for it. The session stays `quoted`; nothing is booked."""
    quote = session.get("quote") or {}
    old, new = float(change["old_total"]), float(change["new_total"])
    # asked_at: a "yes" the customer wrote BEFORE this mail is a yes to the old price and must not book the new one
    repriced = {**quote, "total": new, "rate_id": change["rate_id"], "accepted_total_before": old, "asked_at": time.time(),
                **({"total_eur": round(float(quote.get("total_eur") or old) * new / old, 2)} if old else {})}
    api.update(session["id"], quote=repriced)
    text = reprice_text(session.get("rfq") or {}, repriced)
    if isinstance(asked_id := box.reply(mail, text), int):  # 5U's ids only grow: an older yes has a smaller id
        api.update(session["id"], quote={**repriced, "asked_mail_id": asked_id})
    api.event(session["id"], "routed", f"Price changed before booking ({change['currency']} {old:,.2f} → "
              f"{change['currency']} {new:,.2f}): customer asked again, not booked", {**change, **reply_data(mail, text)})


def _before_our_new_price(mail: dict, quote: dict) -> bool:
    """The customer wrote this mail before our new-price mail (two quick "yes" mails to the old price). Mail ids
    decide when both are 5U's (no clock skew); else the mail's send time against when we asked."""
    if isinstance(asked_id := quote.get("asked_mail_id"), int) and isinstance(mail.get("id"), int):
        return mail["id"] < asked_id
    return bool(asked := quote.get("asked_at")) and sent_at(mail) < float(asked)


def portal_cannot_book(error: Exception) -> bool:
    response = getattr(error, "response", None)
    return EMAIL_ONLY in (getattr(response, "text", "") or "")


def book_by_email(session: dict, box, api, why: str) -> dict | None:
    """The portal can't book the accepted option (no rate ID, airline not on the portal for the lane, booking down):
    ask the airline by mail, quoting its rate ID from the bid. Its "Booking BK-… confirmed" mail completes the
    booking (handle_booking_confirmed). Every booking earns the +10 tracking bonus later. None if no address."""
    quote, rfq = session.get("quote") or {}, session.get("rfq") or {}
    carrier = quote.get("carrier")
    email = airline_email(carrier) if EMAIL_BOOKING else None
    if not email:
        return None
    rate_id = quote.get("rate_id") or next((b.get("rate_id") for b in session.get("bids") or []
                                            if b.get("carrier") == carrier and b.get("leg") != "pickup" and b.get("rate_id")), None)
    reference = f"S-{session['id']}"
    lane = f"{rfq.get('origin')}-{rfq.get('destination')}"
    kg = quote.get("billed_weight_kg") or quote.get("chargeable_weight_kg")
    lines = [f"Please book {'rate ID ' + rate_id if rate_id else 'your offer'} for our shipment {lane}"
             + (f", {kg:,.2f} kg" if isinstance(kg, (int, float)) else "")
             + (f", ready {rfq['ready_date']}" if rfq.get("ready_date") else "") + ".",
             f"Our reference: {reference}.", "", "Please confirm with the booking reference.", "", "Kind regards,",
             "Lena", "Leylü Air Freight"]
    booking = {**(session.get("booking") or {}), "pending_email": email, "airline": carrier, "rate_id": rate_id,
               "team_reference": reference, "requested_at": now(), "status": "requested by email"}
    # Stored BEFORE the mail goes out: a backend blip after sending must not let the next "yes" mail the airline
    # again (bookings are public and can't be cancelled). needs_human stays on until the confirmation is matched.
    api.update(session["id"], stage="booked", outcome="won", booking=booking,
               needs_human=not EMAIL_WAIT_QUIET)
    box.send(email, f"Booking request {lane}" + (f" {rate_id}" if rate_id else ""), "Hello,\n\n" + "\n".join(lines))
    api.event(session["id"], "booked", f"Booking requested by email from {carrier} (portal: {why[:120]})", booking)
    api.event(session["id"], "needs_human" if not EMAIL_WAIT_QUIET else "routed",
              f"Booking requested by email from {carrier}, waiting for the airline's confirmation")
    return booking


def booking_requested_text(session: dict) -> str:
    name = (session.get("rfq") or {}).get("contact_name")
    airline = (session.get("quote") or {}).get("carrier") or "the airline"
    return (f"{'Hi ' + name.split()[0] + ',' if name else 'Hi,'}\n\nGreat, I've asked {airline} to book it for you. "
            "I'll send you the booking reference as soon as the airline confirms.\n\nBest regards,\nLena\nLeylü Air Freight")


def handle_customer_reply(mail: dict, box, api, session: dict | None) -> None:
    if session is None:  # no session for this thread: nothing to book or hand over, but never crash the worker
        return print(f"reply without a session ignored: #{mail.get('id')} {mail.get('from')}")
    session_id = session["id"]
    api.event(session_id, "mail_in", f"Reply from {mail['from']}: {mail['subject']}", mail_data(mail))
    try:
        # Only while the RFQ agent still prices: a handed-over or paused session goes to a person as before.
        if session.get("stage") in ("new", "pricing") and not (session.get("needs_human") or session.get("paused")):  # a correction while we price: the RFQ agent re-reads it
            amendments.add(mail["thread_id"], mail)
            return api.event(session_id, "routed", "Customer wrote again before our quote: read with the request")
        if session.get("stage") != "quoted":
            text = _plain(latest_text(mail["body"]))
            requested = bool((session.get("booking") or {}).get("pending_email"))  # booked by email, not confirmed yet
            if (is_booked(session) or requested) and THANKS.search(text) and "?" not in text and not DECLINE.search(text):
                # "Thank you for booking, let me know once the airline confirms": the confirmation mail answers it
                return api.event(session_id, "routed", "Customer thanked us after the booking (no reply needed)")
            if TRACKING_IN_THREAD and is_booked(session) and is_status_question(text) \
                    and not api.session(session_id).get("paused"):
                reply = tracking_text(session)
                box.reply(mail, reply)
                return api.event(session_id, "tracking_answer", f"Status question in the booking thread answered "
                                                                f"({mail['from']})", reply_data(mail, reply))
            return hand_over(api, session_id, "Customer wrote, but there is no open quote")
        intent, cost = read_intent(mail["body"])
        if cost:
            api.update(session_id, llm_cost_usd=(session.get("llm_cost_usd") or 0) + cost)
        if intent == "decline":
            api.update(session_id, stage="done", outcome="lost")
            return api.event(session_id, "declined", "Customer declined the quote", cost=cost)
        text = _plain(latest_text(mail["body"]))
        rfq = session.get("rfq") or {}
        if intent != "accept" and intent != "wait" and DOCS_BOOK and rfq.get("dangerous_goods") \
                and (mail.get("attachments") or DOCS_SENT.search(text)) and DOCS_PROMISE_WORDS.search(text) \
                and "?" not in text and not CHANGE.search(text) and not CONDITION.search(text):
            intent = "accept"  # the DG papers we waited for are here: book as quoted
            api.event(session_id, "routed", "DG documents received: booking as quoted")
        if CONFIRM_ANSWERS and intent != "accept" and CONFIRM_Q.search(text) and not CONDITION.search(text) \
                and confirms_our_data(text, rfq) \
                and not NOT_PLAIN_QUOTE.search(THANKS_UPDATE.sub(" ", text)) \
                and (session.get("quote") or {}).get("total") and not api.session(session_id).get("paused"):
            # R60: "Please hold off on booking… Could you please confirm that your offer covers 11 pieces, 1,674 kg…?"
            reply = confirm_text(rfq, session["quote"])
            box.reply(mail, reply)
            return api.event(session_id, "routed", "Customer asked us to confirm the quote: confirmed, quote stays open",
                             reply_data(mail, reply), cost)
        if intent == "wait" or (intent != "accept" and "?" not in text and LATER.search(text)
                                and not CHANGE.search(text) and not CONDITION.search(text)):
            return api.event(session_id, "routed", "Customer will decide later: quote stays open, no reply needed",
                             cost=cost)
        if intent != "accept":
            if DOCS_ACK and "?" not in text and DOCS_PROMISE.search(text) and not CHANGE.search(text) \
                    and not CONDITION.search(text) and not api.session(session_id).get("paused"):
                reply = docs_ack_text(session.get("rfq") or {}, session.get("quote") or {})
                box.reply(mail, reply)
                return api.event(session_id, "routed", "Customer will send documents: thanked, ready to book on their word",
                                 reply_data(mail, reply), cost)
            if QUOTE_ANSWERS and not CHANGE.search(THANKS_UPDATE.sub(" ", text)) and not CONDITION.search(text) \
                    and not NOT_PLAIN_QUOTE.search(THANKS_UPDATE.sub(" ", text)) \
                    and (session.get("quote") or {}).get("total") and not api.session(session_id).get("paused"):
                answered = int(rfq.get("auto_answers") or 0)
                topic, topic_cost = (llm.chat_json("topic", TOPIC_PROMPT, text, TOPIC_SCHEMA) if answered < AUTO_ANSWERS
                                     else ({"topic": "other"}, 0.0))
                if topic.get("topic", "other") != "other":
                    reply = quote_style.quote_summary_text(rfq, session["quote"], mail["body"])
                    box.reply(mail, reply)
                    api.update(session_id, rfq={**rfq, "auto_answers": answered + 1})
                    return api.event(session_id, "routed", f"Customer asked about the quote ({topic.get('topic')}): answered",
                                     reply_data(mail, reply), cost + topic_cost)
            return hand_over(api, session_id, "Customer replied with a question")
        with _session_lock(session_id):
            current = api.session(session_id)  # another reply may have booked it in the meantime
            if is_booked(current) or current.get("stage") != "quoted":
                return api.event(session_id, "accepted", "Already booked: second acceptance ignored", cost=cost)
            if _before_our_new_price(mail, current.get("quote") or {}):
                return api.event(session_id, "routed", "A yes to the old price, written before our new-price mail: "
                                 "not booked, waiting for their answer to the new price", cost=cost)
            api.event(session_id, "accepted", "Customer accepted the quote", cost=cost)
            try:
                booking = api.book(session_id, current["quote"].get("rate_id"))
            except Exception as error:  # the portal can't book this option at all: book by email instead
                if change := price_changed(error):  # never book another price than the one accepted (R48, R49)
                    return ask_again_at_new_price(mail, box, api, api.session(session_id), change)
                if not portal_cannot_book(error):
                    raise  # timeout, 502, portal down: it may have booked, so a person checks (as before)
                latest = api.session(session_id)
                if is_booked(latest):  # booked after all: carry on with that booking
                    booking = latest["booking"]
                elif book_by_email(latest, box, api, getattr(getattr(error, "response", None), "text", "")[:200]):
                    text = booking_requested_text(latest)
                    box.reply(mail, text)
                    return api.event(session_id, "routed", "Customer told the booking is requested",
                                     reply_data(mail, text))
                else:
                    raise
            # Store it before anything else: bookings are real and public, a pause must not lose one.
            api.update(session_id, stage="booked", outcome="won", booking={**booking, "booked_at": now()})
        if api.session(session_id).get("paused"):
            return api.event(session_id, "booked", f"Booked {booking['booking_reference']}; mail held: paused", booking)
        text = booking_text(session["rfq"], booking)
        box.reply(mail, text)
        api.event(session_id, "booked", f"Booked with {booking['airline']}: {booking['booking_reference']}",
                  {**booking, **reply_data(mail, text)})
    except Exception as error:  # the session shows what happened; the worker keeps going
        api.update(session_id, needs_human=True)
        api.event(session_id, "error", f"{type(error).__name__}: {error}")


def handle_booking_confirmed(mail: dict, box, api) -> bool:
    """The airline confirmed a booking: record it and tell the customer. False if the mail isn't one."""
    match = CONFIRMED.search(f"{mail['subject']}\n{mail['body']}")
    if not match:
        return False
    reference = match.group(1).upper()
    session = api.find(reference=reference)
    by_email = session is None and (session := _email_booking_of(mail, api)) is not None
    if session is None:
        print(f"confirmation for unknown booking {reference}")
        return True
    update = {"at": now(), "text": f"Booking {reference} confirmed by the airline"}
    booking = {**(session.get("booking") or {}), "booking_reference": reference, "status": "confirmed"}
    session = {**session, "booking": booking}  # R46: the confirmation text needs the reference (KeyError before)
    api.update(session["id"], booking=booking,
               **({"needs_human": False} if by_email else {}),
               status_updates=[*(session.get("status_updates") or []), update])
    data = {}
    if not session.get("paused"):
        thread = {"id": session["thread_id"], "thread_id": session["thread_id"], "from": session["customer"],
                  "subject": "Your air freight booking"}
        text = booking_confirmed_text(session)
        box.reply(thread, text)
        data = reply_data(thread, text)
    api.event(session["id"], "status_sent", update["text"], data)
    return True


def _email_booking_of(mail: dict, api) -> dict | None:
    """The newest session that asked this airline to book by email and has no booking reference yet."""
    sender = parseaddr(mail.get("from") or "")[1].lower()  # "Meridian Freightways <meridian-…@…>" too
    try:
        waiting = [s for s in api.sessions() if (s.get("booking") or {}).get("pending_email") == sender
                   and not (s.get("booking") or {}).get("booking_reference")]
    except Exception:  # a lookup hiccup must not lose the airline's mail: it is still logged as unknown
        return None
    return max(waiting, key=lambda s: s["id"], default=None)
