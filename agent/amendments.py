"""Customer mails that arrive in an RFQ thread before our quote ("correction: it's 850 kg, not 715").

The booking agent parks them here; the RFQ agent, still collecting bids, reads the request again with them before it
quotes, so the one quote that counts uses the corrected figures. In memory: the RFQ and the reply are handled by the
same worker process (a restart loses the RFQ anyway).
"""

import threading

_pending: dict = {}
_lock = threading.Lock()


def add(thread_id, mail: dict) -> None:
    with _lock:
        _pending.setdefault(thread_id, []).append(mail)


def take(thread_id) -> list[dict]:
    """The parked mails of this thread, oldest first, and forgets them."""
    with _lock:
        return _pending.pop(thread_id, [])
