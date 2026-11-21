"""Customer mails that arrive in an RFQ thread before our quote ("correction: it's 850 kg, not 715").

The booking agent parks them here; the RFQ agent, still collecting bids, reads the request again with them before it
quotes, so the one quote that counts uses the corrected figures. In memory: the RFQ and the reply are handled by the
same worker process (a restart loses the RFQ anyway).

Three kill switches (env + restart, `off` = the behaviour before):
- EARLY_CORRECTION: a correction that comes in the same poll as its RFQ, before the RFQ's session exists, is parked
  here too (main.dispatch) instead of being answered as a second RFQ in the same thread (two quotes, the first one
  with the old figures).
- CORRECTION_KEEPS: the re-read keeps what came from outside the mail text: the airlines the customer ruled out (R42).
- CORRECTION_BIDS: carrier bids asked for the old figures are no price for the corrected request: an air bid is
  dropped when the lane, the chargeable weight or the dangerous-goods flag changed, a pickup bid when the pickup zone
  changed. Sheets and the portal are priced again anyway.
"""

import os
import threading
import time

from carriers import pickup_zone

EARLY_CORRECTION = os.environ.get("EARLY_CORRECTION", "on").lower() != "off"
CORRECTION_KEEPS = os.environ.get("CORRECTION_KEEPS", "on").lower() != "off"
CORRECTION_BIDS = os.environ.get("CORRECTION_BIDS", "on").lower() != "off"
RFQ_LIFETIME_SECONDS = 360  # 5U: an RFQ expires 6 minutes after it is sent

_pending: dict = {}
_started: dict = {}  # thread id → when its RFQ was handed to the RFQ agent
_lock = threading.Lock()


def add(thread_id, mail: dict) -> None:
    with _lock:
        _pending.setdefault(thread_id, []).append(mail)


def take(thread_id) -> list[dict]:
    """The parked mails of this thread, oldest first, and forgets them."""
    with _lock:
        return _pending.pop(thread_id, [])


_held: set = set()  # threads whose quote the gate holds right now (rfq_agent._hold)


def holding(thread_id, on: bool) -> None:
    with _lock:
        (_held.add if on else _held.discard)(thread_id)


def held(thread_id) -> bool:
    """The RFQ agent holds this thread's quote: a customer mail now is still read before the quote goes out."""
    with _lock:
        return thread_id in _held


def waiting(thread_id) -> bool:
    with _lock:
        return bool(_pending.get(thread_id))


def started(thread_id) -> None:
    """main.dispatch: the RFQ of this thread is being priced from now on."""
    with _lock:
        now = time.time()
        for old in [t for t, at in _started.items() if now - at > RFQ_LIFETIME_SECONDS]:
            _started.pop(old, None)
        _started[thread_id] = now


def in_progress(thread_id) -> bool:
    """The RFQ of this thread is still being priced in this process (its session may not exist yet)."""
    with _lock:
        at = _started.get(thread_id)
    return at is not None and time.time() - at <= RFQ_LIFETIME_SECONDS


def carry_over(old: dict, new: dict) -> dict:
    """The re-read rfq with what the first reading had from outside the mail text: the airlines ruled out."""
    if not CORRECTION_KEEPS:
        return new
    excluded = list(old.get("excluded_airlines") or [])
    excluded += [x for x in new.get("excluded_airlines") or [] if x not in excluded]
    return {**new, "excluded_airlines": excluded} if excluded else new


def still_valid(old: dict, new: dict, bids: list[dict], chargeable) -> tuple[list[dict], list[dict]]:
    """(bids that still price the corrected request, bids that don't). chargeable: rfq → billed kg or None."""
    if not CORRECTION_BIDS or not bids:
        return list(bids), []
    lane = lambda r: ((r.get("origin") or "").upper(), (r.get("destination") or "").upper())  # noqa: E731
    before, after = chargeable(old), chargeable(new)
    weight_changed = (before != after) if None in (before, after) else abs(after - before) > max(0.5, 0.005 * before)
    air_changed = lane(old) != lane(new) or weight_changed or bool(old.get("dangerous_goods")) != bool(
        new.get("dangerous_goods"))
    pickup_changed = pickup_zone(old.get("pickup")) != pickup_zone(new.get("pickup"))
    kept, dropped = [], []
    for b in bids:
        stale = pickup_changed if b.get("leg") == "pickup" else air_changed
        (dropped if stale else kept).append(b)
    return kept, dropped
