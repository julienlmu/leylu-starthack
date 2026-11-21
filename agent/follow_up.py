"""FOLLOW_UP: one short reminder in the customer's thread when our quote got no answer 2:30 after we sent it.

Since R54 5U's customers often stay silent after the quote, and only a booking earns the +10 tracking points. The
reminder asks "shall I go ahead and book <airline>?" and never states an amount. It books nothing: a yes to it runs the
normal booking flow (booking_agent.handle_customer_reply). Rules and a template, no LLM call.

At most one per session, and none when:
- the customer wrote anything after the quote (yes, no, hold, question), or a person stepped in (paused, intervened);
- the session ever needed a person (gate hold, hand-over, fallback quote) or logged an error;
- it is a DG quote (it waits for the DG papers), a quote a person wrote by hand (`by: person`), or already booked;
- the quote is older than 15 minutes (e.g. a long restart): that round is over.
Spam and phishing RFQs never get a quote, so they never reach this.

The sent flag is stored on the quote (`follow_up_sent_at`) before the mail goes out, so a restart or a crash right
after sending never sends a second one. The worker sweeps quoted sessions every few seconds in its own thread.
Default OFF (customers reply again since R57): FOLLOW_UP=on switches it on.
"""

import os
import threading
import time
from datetime import datetime, timezone

from backend import now
from booking_agent import _session_lock, is_booked
from inbox import reply_data
from templates import quote_reminder_text

FOLLOW_UP = os.environ.get("FOLLOW_UP", "off").lower() == "on"
FOLLOW_UP_AFTER_SECONDS = float(os.environ.get("FOLLOW_UP_AFTER_SECONDS", "150"))
FOLLOW_UP_LATEST_SECONDS = 900
SWEEP_SECONDS = 5
# After our quote, any of these means the customer or a person already answered: no reminder.
ANSWERED = {"mail_in", "accepted", "declined", "booked", "intervened", "tracking_answer", "status_sent"}
# Anywhere in the session: a person was (or is) needed, so the quote was not a plain one.
NOT_PLAIN = {"needs_human", "error"}

_replied: dict = {}  # thread id -> time this worker saw a customer mail in it (before its handler logged it)
_sent: set = set()   # session ids this worker followed up (the stored flag covers restarts)


def saw_reply(thread_id) -> None:
    """The worker routed a customer mail in this thread: its handler may not have logged it yet."""
    _replied[str(thread_id)] = time.time()


def _epoch(stamp) -> float | None:
    try:
        at = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).timestamp()


def due(session: dict, t: float | None = None) -> bool:
    """The stored session alone says a reminder is due (events are checked in send())."""
    quote, rfq, booking = session.get("quote") or {}, session.get("rfq") or {}, session.get("booking") or {}
    if session.get("stage") != "quoted" or session.get("outcome", "open") != "open" or session.get("paused") \
            or session.get("needs_human") or is_booked(session) or booking.get("pending_email"):
        return False
    if quote.get("follow_up_sent_at") or session.get("id") in _sent or quote.get("asked_at") or quote.get("fallback") \
            or quote.get("by") == "person":
        return False  # sent already, we asked about a new price (the customer owes us that answer), or a person quoted
    if rfq.get("dangerous_goods") or not quote.get("total") or not quote.get("carrier"):
        return False
    sent = _epoch(quote.get("sent_at")) if quote.get("sent_at") else None
    if sent is None:
        return False
    if _replied.get(str(session.get("thread_id")), 0) >= sent:
        return False
    age = (time.time() if t is None else t) - sent
    return FOLLOW_UP_AFTER_SECONDS <= age <= FOLLOW_UP_LATEST_SECONDS


def quiet(events: list[dict]) -> bool:
    """Our quote is the last word in the thread, and nothing ever needed a person."""
    quoted = [i for i, e in enumerate(events) if e.get("kind") == "quote_sent"]
    if not quoted or any(e.get("kind") in NOT_PLAIN for e in events):
        return False
    return not any(e.get("kind") in ANSWERED for e in events[quoted[-1] + 1:])


def send(session: dict, box, api) -> bool:
    """One reminder, if it is still due. True if it went out."""
    session_id = session["id"]
    with _session_lock(session_id):  # booking_agent books a yes under the same lock: never both at once
        current = api.session(session_id)
        if not due(current):
            return False
        events = api.events(session_id)
        if not quiet(events):
            return False
        quote = {**current["quote"], "follow_up_sent_at": now()}
        _sent.add(session_id)
        api.update(session_id, quote=quote)  # stored BEFORE the mail: a crash after sending never sends a second one
    ours = next((e.get("data") or {} for e in reversed(events) if e.get("kind") == "quote_sent"), {})
    thread = {"id": current["thread_id"], "thread_id": current["thread_id"], "from": current["customer"],
              "to": ours.get("from"), "subject": ours.get("subject") or "Your air freight quote"}
    text = quote_reminder_text(current.get("rfq") or {}, quote)
    box.reply(thread, text)
    waited = time.time() - (_epoch(quote["sent_at"]) or time.time())
    api.event(session_id, "routed", f"Follow-up sent: no answer {waited:.0f} s after our quote (no amount, books nothing)",
              {**reply_data(thread, text), "follow_up": True})
    return True


def sweep(box, api, t: float | None = None) -> list[int]:
    """Sends every reminder that is due. Never raises: the worker keeps going."""
    if not FOLLOW_UP:
        return []
    try:
        sessions = api.sessions(stage="quoted")
    except Exception as error:
        print(f"follow-up: sessions not readable: {type(error).__name__}: {error}")
        return []
    sent = []
    for s in sessions:
        if not due(s, t):
            continue
        try:
            if send(s, box, api):
                sent.append(s["id"])
        except Exception as error:
            print(f"follow-up for session {s.get('id')} failed: {type(error).__name__}: {error}")
    return sent


def start(box, api) -> None:
    """Sweeps in its own thread, so a slow backend or mailbox never delays the mail poll."""
    if not FOLLOW_UP:
        return

    def loop():
        while True:
            sweep(box, api)
            time.sleep(SWEEP_SECONDS)

    threading.Thread(target=loop, daemon=True, name="follow-up").start()
