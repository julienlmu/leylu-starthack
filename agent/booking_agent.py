"""Booking agent: a customer reply to our quote → accept / decline / question → book by rate ID and confirm.

Also records the airline's "Booking BK-… confirmed" mail and tells the customer.
"""

import re

import llm
from backend import now
from rfq_agent import hand_over
from router import CONFIRMED
from templates import booking_confirmed_text, booking_text

# Replies quote our own mail below theirs; only the new text counts ("…we'll book it" is ours).
QUOTED = re.compile(r"^(>|On .+ wrote:|Am .+ schrieb|Le .+ a écrit|El .+ escribió|-----Original|From:|Von:)", re.I)
ACCEPT = re.compile(r"\b(accept\w*|book\w*|go ahead|confirm\w*|agreed|deal|ok|okay|yes|einverstanden|buchen|"
                    r"bestätig\w*|d'accord|réserve\w*|acepto|reserv\w*|akceptuj\w*|zgoda)\b", re.I)
DECLINE = re.compile(r"\b(no|not|don't|decline\w*|cancel\w*|expensive|nicht|kein\w*|teuer|absage\w*|pas|annule\w*|"
                     r"caro|nie)\b", re.I)
INTENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent"],
    "properties": {"intent": {"type": "string", "enum": ["accept", "decline", "question", "other"]}},
}


def latest_text(body: str) -> str:
    lines = []
    for line in body.splitlines():
        if QUOTED.match(line.strip()):
            break
        lines.append(line)
    return "\n".join(lines)


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
    api.event(session_id, "mail_in", f"Reply from {mail['from']}: {mail['subject']}")
    try:
        if session.get("stage") != "quoted":
            return hand_over(api, session_id, "Customer wrote, but there is no open quote")
        intent, cost = read_intent(mail["body"])
        if cost:
            api.update(session_id, llm_cost_usd=(session.get("llm_cost_usd") or 0) + cost)
        if intent == "decline":
            api.update(session_id, stage="done", outcome="lost")
            return api.event(session_id, "declined", "Customer declined the quote", cost=cost)
        if intent != "accept":
            return hand_over(api, session_id, "Customer replied with a question")
        api.event(session_id, "accepted", "Customer accepted the quote", cost=cost)

        quote = session["quote"]
        booking = api.book(session_id, quote.get("rate_id"))
        if api.session(session_id).get("paused"):
            return
        box.reply(mail, booking_text(session["rfq"], booking))
        api.update(session_id, stage="booked", outcome="won", booking={**booking, "booked_at": now()})
        api.event(session_id, "booked", f"Booked with {booking['airline']}: {booking['booking_reference']}", booking)
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
               status_updates=[*session.get("status_updates", []), update])
    api.event(session["id"], "status_sent", update["text"])
    if not session.get("paused"):
        box.reply({"id": session["thread_id"], "thread_id": session["thread_id"], "from": session["customer"],
                   "subject": "Your air freight booking"},
                  booking_confirmed_text(session))
    return True
