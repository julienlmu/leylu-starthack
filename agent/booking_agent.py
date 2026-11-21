"""Booking agent: a customer reply to our quote → accept / decline / question → book by rate ID and confirm.

Also records the airline's "Booking BK-… confirmed" mail and tells the customer.
"""

import re
import threading

import llm
from backend import now
from inbox import latest_text, mail_data, reply_data
from rfq_agent import hand_over
from router import CONFIRMED
from templates import booking_confirmed_text, booking_text

ACCEPT = re.compile(r"\b(accept\w*|book\w*|go ahead|confirm\w*|agreed|deal|ok|okay|yes|einverstanden|buchen|"
                    r"bestätig\w*|d'accord|réserve\w*|acepto|reserv\w*|akceptuj\w*|zgoda)\b", re.I)
# After a booking, only a plain thank-you needs no person: "please cancel" or "change the date" must still reach one.
THANKS = re.compile(r"\b(thank\w*|thx|cheers|dank\w*|merci|gracias|grazie|obrigad\w*|dzięk\w*|bedank\w*)\b", re.I)
DECLINE = re.compile(r"\b(no|not|don't|decline\w*|cancel\w*|expensive|nicht|kein\w*|teuer|absage\w*|pas|annule\w*|"
                     r"caro|nie)\b", re.I)
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
    yes, no = bool(ACCEPT.search(text)), bool(DECLINE.search(text))
    if yes and not no and "?" not in text:  # "ok, but can you do it cheaper?" must not book
        return "accept", 0.0
    if no and not yes:
        return "decline", 0.0
    data, cost = llm.chat_json("intent", "Does the customer accept our freight quote, decline it, or ask a question?",
                               text, INTENT_SCHEMA)
    return data["intent"], cost


def handle_customer_reply(mail: dict, box, api, session: dict) -> None:
    session_id = session["id"]
    api.event(session_id, "mail_in", f"Reply from {mail['from']}: {mail['subject']}", mail_data(mail))
    try:
        if session.get("stage") != "quoted":
            text = latest_text(mail["body"])
            if is_booked(session) and THANKS.search(text) and "?" not in text and not DECLINE.search(text):
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
            booking = api.book(session_id, current["quote"].get("rate_id"))
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
    if session is None:
        print(f"confirmation for unknown booking {reference}")
        return True
    update = {"at": now(), "text": f"Booking {reference} confirmed by the airline"}
    api.update(session["id"], booking={**session["booking"], "status": "confirmed"},
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
