"""Tracking agent: answers "where is it?" from tracking@ out of our own CRM. No LLM, no portal call (there is none).

5U's tracking questions often name no reference at all ("Sonnberg Kaffeeroesterei GmbH, 61018 to JFK, 1233 kg,
ready on 2026-11-25"). Then the booked shipment is found by what the question repeats from its RFQ (tracking_match).

Order: exact reference (backend lookup) → a reference typed another way or with one typo (TRACKING_FUZZY) → the
shipment's details → the customer thread the question arrived in (TRACKING_IN_THREAD) → the company / contact name
(TRACKING_CUSTOMER). A quoted BK- number we can't place stops the search: someone else's booking, we ask.
Never another customer's booking: every match that is not an exact reference must not contradict the question.
"""

import os
import re

import tracking_match
from inbox import latest_text, reply_data
from booking_agent import is_booked
from templates import SIGNER, tracking_many_text, tracking_text, tracking_unknown_text
from tracking_match import best_match, is_date

# Booking references (BK-1A2B3C4D), our portal team reference (S-12), then anything that looks like a reference
# (PO-4711, AB123456).
REFERENCES = re.compile(r"\bBK-[A-Z0-9]{8}\b|\bS-\d+\b|\b[A-Z0-9]{2,}(?:[-/][A-Z0-9]+)+\b|\b[A-Z]{2,}\d{3,}\b")
BOOKING_REF = re.compile(r"\bBK-[A-Z0-9]{8}\b")
MAX_LOOKUPS = 5
# TRACKING_IN_THREAD=off: a tracking@ mail in a customer's booked thread is matched like any other (as before).
IN_THREAD = os.environ.get("TRACKING_IN_THREAD", "on").lower() != "off"


def handle_tracking(mail: dict, box, api, thread_session: dict | None = None) -> None:
    """thread_session: the session whose thread the mail arrived in (main.dispatch), if any."""
    text = f"{mail['subject']}\n{mail['body']}"
    candidates = [r for r in dict.fromkeys(REFERENCES.findall(text)) if not is_date(r)][:MAX_LOOKUPS]
    fuzzy, customer = tracking_match.FUZZY, tracking_match.CUSTOMER
    found = []
    for ref in candidates:
        if hit := api.find(reference=ref):
            found.append(hit)
            if not fuzzy or is_booked(hit):  # before: the first hit decided, even an unbooked quote with that PO
                break
    session = next((s for s in found if is_booked(s)), found[0] if found else None)
    answers, how = [session], ""
    # A quoted BK- number we don't know is someone else's booking: ask, don't guess from the shipment details.
    unknown_bk = bool(tracking_match.bk_tokens(text) if fuzzy else BOOKING_REF.search(text))
    if session is None or not is_booked(session):
        booked = None
        if fuzzy:
            booked = [s for s in api.booked_sessions() if is_booked(s)]
            hit, how = tracking_match.reference_match(text, booked, mail.get("from") or "",
                                                      thread_session if IN_THREAD else None)
            session = hit or session
            answers = [session]
        if (session is None or not is_booked(session)) and not unknown_bk:
            booked = booked if booked is not None else [s for s in api.booked_sessions() if is_booked(s)]
            session = best_match(text, booked)
            answers = [session]
            if session is None and IN_THREAD and thread_session and is_booked(thread_session) \
                    and (tracking_match.identifies(text, thread_session) or _names_nothing(mail["body"])) \
                    and not tracking_match.contradicts(text, thread_session, booked):
                session, answers, how = thread_session, [thread_session], "the customer's thread"
            if session is None and customer:
                answers = tracking_match.customer_match(text, booked, _all_sessions(api))
                session, how = (answers[0] if answers else None), "the customer's name or address"
    if session is None or not is_booked(session):
        print(f"tracking question without a booked shipment: {candidates}")
        box.reply(mail, tracking_unknown_text())
        return
    answer = tracking_text(session) if len(answers) == 1 else tracking_many_text(answers)
    box.reply(mail, answer)
    note = f", matched by {how}" if how else ""
    for s in answers:
        api.event(s["id"], "tracking_answer", f"Tracking question answered ({mail['from']}{note})", reply_data(mail, answer))


def _names_nothing(body: str) -> bool:
    """"Where is it now?": the new text names no number and no name (no capitalised word inside a sentence), so the
    thread it arrived in is all it can be about. "Huber Optik here, where is ...?" or "status of S-7?" is not."""
    text = latest_text(body)
    if re.search(r"\d", text):
        return False
    for sentence in re.split(r"[.!?\n]+", text):
        words = re.findall(r"[^\W\d_]+", sentence)
        if any(w[0].isupper() and w not in ("I", SIGNER) for w in words[1:]):
            return False
    return True


def _all_sessions(api) -> list[dict] | None:
    """Every session (to see a booking still waiting for its reference); None when the client can't list them."""
    try:
        sessions = api.sessions()
        return sessions if isinstance(sessions, list) else None
    except Exception:
        return None
