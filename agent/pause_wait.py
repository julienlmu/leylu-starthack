"""PAUSE_WAIT (R120): a person paused a session just before our quote went out, resumed it two minutes later, and no
quote was ever sent (the agent saw "paused" at the send and gave up for good). Now a pause at the send waits: on
resume the quote goes out, if the RFQ can still score and nobody answered the customer by hand meanwhile.

Never a second mail in the thread: a person's own reply (the Sessions UI's "Reply sent by a person", with or without a
price read from it), a quote set by hand, or an unreadable event log all mean no automatic quote.
PAUSE_WAIT=off: a pause at the send ends the automatic quote, as before.
"""
import os
import time

ON = os.environ.get("PAUSE_WAIT", "on").lower() != "off"
LATEST_SECONDS = 330  # the RFQ expires at 6:00 after it was sent; a later quote can't score (FALLBACK_LATEST_SECONDS)
POLL_SECONDS = 2.0
_sleep = time.sleep  # tests replace it


def _answered_by_hand(session_id, api) -> bool:
    try:
        events = api.events(session_id)
    except Exception:
        return True  # can't tell: never risk a second mail in the thread
    return any(e.get("kind") == "quote_sent" or (e.get("kind") == "intervened" and "sent by a person" in
               (e.get("text") or "")) for e in events or [])


def cleared(session_id, sent_at: float, api, current: dict | None = None) -> bool:
    """True = send the automatic quote now. False = a person quoted or answered, or the RFQ ran out while paused.
    sent_at: when the customer sent the RFQ (epoch seconds)."""
    current = current if current is not None else api.session(session_id)
    if current.get("quote"):
        return False
    if not current.get("paused"):
        return True
    if not ON:
        return False
    api.event(session_id, "routed", "Paused by a person at the quote: waiting, the quote goes out on resume "
                                     f"(until {LATEST_SECONDS // 60}:{LATEST_SECONDS % 60:02d} after the RFQ)")
    while time.time() < sent_at + LATEST_SECONDS:
        _sleep(POLL_SECONDS)
        try:
            current = api.session(session_id)
        except Exception:  # a backend hiccup (e.g. a restart) must not end the wait
            continue
        if current.get("quote"):
            return False
        if not current.get("paused"):
            if _answered_by_hand(session_id, api):
                api.event(session_id, "routed", "Resumed after a person answered the customer: no automatic quote")
                return False
            if time.time() > sent_at + LATEST_SECONDS:
                break
            api.event(session_id, "routed", "Resumed: the quote goes out now")
            return True
    api.event(session_id, "needs_human", "Still paused when the RFQ ran out: no quote sent")
    return False
