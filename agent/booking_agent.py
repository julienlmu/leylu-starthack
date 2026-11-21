"""Booking agent: a customer reply to our quote → accept / decline / question → book by rate ID and confirm.

Also records the airline's "Booking BK-… confirmed" mail and tells the customer.
"""

import os
from email.utils import parseaddr
import re
import threading

import amendments
import llm
from backend import now
from carriers import load_carriers
from inbox import latest_text, mail_data, reply_data
from rfq_agent import hand_over
from router import CONFIRMED
from templates import booking_confirmed_text, booking_text

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
INTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent"],
    "properties": {"intent": {"type": "string", "enum": ["accept", "decline", "question", "other"]}},
}


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
    text = latest_text(body)
    # "we will not go ahead with it" / "won't book": a negated yes is a no, not a mixed reply (5U's rejection notices)
    refused = NEGATED_ACCEPT.search(text)
    yes = bool(ACCEPT.search(NEGATED_ACCEPT.sub(" ", text)))
    no = bool(refused or DECLINE.search(NO_OBJECTION.sub(" ", text)))
    changed = bool(CHANGE.search(text) or CONDITION.search(text))
    if yes and not no and "?" not in text and not changed:  # "ok, but can you do it cheaper?" must not book
        return "accept", 0.0
    if no and not yes:
        return "decline", 0.0
    data, cost = llm.chat_json("intent", "Does the customer accept our freight quote, decline it, or ask a question?",
                               text, INTENT_SCHEMA)
    # "Yes, but 2 pallets fewer" / "OK if 10% cheaper": never booked as quoted, even when the model calls it a yes
    return ("question" if changed and data["intent"] == "accept" else data["intent"]), cost


EMAIL_BOOKING = os.environ.get("EMAIL_BOOKING", "on") != "off"  # off: a failed portal booking goes to a person again
# The only failure that means "the portal can't book this at all" (backend/booking.py: no portal rate ID and the airline
# isn't on the portal for the lane). A 502 from a timeout or an unreachable portal may have booked: never mail then.
EMAIL_ONLY = "book it by email with the airline"
_airlines: dict[str, str] = {}


def airline_email(name: str | None) -> str | None:
    """The carrier list's address for an airline name ("Meridian Freightways" → meridian-freightways@…)."""
    if not _airlines:
        _airlines.update({c["name"].lower(): c["email"] for c in load_carriers() if c.get("kind") == "airline"})
    return _airlines.get((name or "").strip().lower())


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
    api.update(session["id"], stage="booked", outcome="won", booking=booking, needs_human=True)
    box.send(email, f"Booking request {lane}" + (f" {rate_id}" if rate_id else ""), "Hello,\n\n" + "\n".join(lines))
    api.event(session["id"], "booked", f"Booking requested by email from {carrier} (portal: {why[:120]})", booking)
    api.event(session["id"], "needs_human", f"Booking requested by email from {carrier}, waiting for the airline's "
                                            f"confirmation: check its reply if none arrives")
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
            text = latest_text(mail["body"])
            requested = bool((session.get("booking") or {}).get("pending_email"))  # booked by email, not confirmed yet
            if (is_booked(session) or requested) and THANKS.search(text) and "?" not in text and not DECLINE.search(text):
                # "Thank you for booking, let me know once the airline confirms": the confirmation mail answers it
                return api.event(session_id, "routed", "Customer thanked us after the booking (no reply needed)")
            return hand_over(api, session_id, "Customer wrote, but there is no open quote")
        intent, cost = read_intent(mail["body"])
        if cost:
            api.update(session_id, llm_cost_usd=(session.get("llm_cost_usd") or 0) + cost)
        if intent == "decline":
            api.update(session_id, stage="done", outcome="lost")
            return api.event(session_id, "declined", "Customer declined the quote", cost=cost)
        if intent != "accept":
            return hand_over(api, session_id, "Customer replied with a question")
        with _session_lock(session_id):
            current = api.session(session_id)  # another reply may have booked it in the meantime
            if is_booked(current) or current.get("stage") != "quoted":
                return api.event(session_id, "accepted", "Already booked: second acceptance ignored", cost=cost)
            api.event(session_id, "accepted", "Customer accepted the quote", cost=cost)
            try:
                booking = api.book(session_id, current["quote"].get("rate_id"))
            except Exception as error:  # the portal can't book this option at all: book by email instead
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
    api.update(session["id"], booking={**session["booking"], "booking_reference": reference, "status": "confirmed"},
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
