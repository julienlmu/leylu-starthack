"""Worker: polls the mailbox, routes every mail and hands it to an agent in its own thread.

Run live:   uv run --env-file ../.env python main.py          (needs FIVEU_API_KEY and the backend on BACKEND_URL)
Run local:  MOCK=1 uv run --env-file ../.env python main.py   (mails from fixtures/inbox, nothing is sent; the
            LLM still needs the key, and sessions go to BACKEND_URL, so point it at a local backend)
"""

import base64
import fcntl
import os
import tempfile
import threading
import time

from backend import Backend
from bids import BidBoard
from booking_agent import handle_booking_confirmed, handle_customer_reply
from carriers import KIT_LIST, load_carriers
from inbox import FiveUMailbox, FixtureMailbox
from rfq_agent import resume_after_pickup, BID_CUTOFF_SECONDS, handle_rfq, sent_at
from router import route
from tracking_agent import handle_tracking

POLL_SECONDS = 1.5  # 5U: "response time counts: poll every second or two"
RETRY_SECONDS = 300  # an RFQ expires 6 min after it was sent: retry a failed dispatch until then, then give up
RFQ_LIFETIME_SECONDS = 360  # 5U: every RFQ expires 6 minutes after it is sent; an older one can't score


def main() -> None:
    live = os.environ.get("FIVEU_API_KEY") and os.environ.get("MOCK") != "1"
    _lock = single_worker_lock() if live else None  # held as long as main() runs, released when the process dies
    box = FiveUMailbox() if live else FixtureMailbox(os.environ.get("FIXTURE_INBOX", "fixtures/inbox"))
    api = Backend()
    board = BidBoard()
    carriers = load_carriers(os.environ.get("CARRIERS_FILE") or KIT_LIST)
    print(f"worker running ({'live 5U mailbox' if live else 'fixtures'}), {len(carriers)} carriers")
    failed: dict = {}
    max_rfq_age = RFQ_LIFETIME_SECONDS if live else None  # fixture mails carry old timestamps
    if live:
        resume_unfinished(box, api, board, carriers)
    while True:
        poll_once(box, api, board, carriers, failed, max_rfq_age)
        time.sleep(POLL_SECONDS)


RESUME_MIN_LEFT_SECONDS = 30  # less than this left of the RFQ's 6 minutes: a quote can't reach 5U in time


def resume_unfinished(box, api, board: BidBoard, carriers: list[dict]) -> list[int]:
    """After a restart: RFQs that were being priced when the worker stopped get priced and quoted now, if they can
    still score. The mailbox poll has moved past their mail, so each one is fetched again by its thread id.

    shortcut: a crash between sending the quote and storing it (one backend call) would quote twice; that window is
    a few milliseconds, the RFQs it rescues are minutes.
    """
    try:
        sessions = api.sessions()
    except Exception as error:  # backend not up yet: nothing to resume, never block the worker
        print(f"resume: sessions not readable: {type(error).__name__}: {error}")
        return []
    resumed = []
    for s in sessions:
        if s.get("stage") not in ("new", "pricing") or s.get("quote") or s.get("paused") or s.get("needs_human"):
            continue
        if (s.get("rfq") or {}).get("awaiting"):
            continue  # we asked the customer: their answer resumes it (resume_after_pickup)
        if time.time() - sent_at({"received_at": s.get("received_at")}) > RFQ_LIFETIME_SECONDS - RESUME_MIN_LEFT_SECONDS:
            continue  # expired (no received_at counts as now, the mail's own time decides below)
        try:
            mail = box.get(s["thread_id"])
            if time.time() - sent_at(mail) > RFQ_LIFETIME_SECONDS - RESUME_MIN_LEFT_SECONDS:
                continue
        except Exception as error:
            print(f"resume: mail {s.get('thread_id')} not readable: {type(error).__name__}: {error}")
            continue
        print(f"resume: session {s['id']} (mail #{mail['id']}): pricing again")
        _start(handle_rfq, mail, box, api, board, carriers, BID_CUTOFF_SECONDS, s["id"])
        resumed.append(s["id"])
    return resumed


def single_worker_lock():
    """Two workers on one mailbox would both answer every RFQ. The OS releases the lock when the process dies,
    even on kill -9, so a crash never leaves it stuck."""
    path = os.environ.get("WORKER_LOCK_FILE", os.path.join(tempfile.gettempdir(), "leylu-5u-worker.lock"))
    handle = open(path, "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise SystemExit(f"another worker already polls the 5U mailbox (lock {path}): stop it first")
    return handle


def poll_once(box, api, board: BidBoard, carriers: list[dict], failed: dict, max_rfq_age: float | None = None) -> None:
    """Fetches new mail and dispatches it, plus every mail whose dispatch failed before.

    The mailbox has already moved past a fetched mail, so a dispatch that fails (e.g. the backend restarts for a few
    seconds) would lose it for good. `failed` keeps it: mail id -> (mail, time of the first failure).
    """
    try:
        mails = box.fetch()
    except Exception as error:  # network blip or 5U hiccup: keep polling all night
        print(f"poll failed: {type(error).__name__}: {error}")
        mails = []
    for mail in [m for m, _ in failed.values()] + mails:
        try:
            dispatch(mail, box, api, board, carriers, max_rfq_age)
            failed.pop(mail["id"], None)
        except Exception as error:
            first = failed.get(mail["id"], (mail, time.time()))[1]
            keep = time.time() - first < RETRY_SECONDS
            if keep:
                failed[mail["id"]] = (mail, first)
            else:
                failed.pop(mail["id"], None)
            print(f"dispatch failed for mail {mail.get('id')} ({'will retry' if keep else 'giving up'}): "
                  f"{type(error).__name__}: {error}")


def dispatch(mail: dict, box, api, board: BidBoard, carriers: list[dict], max_rfq_age: float | None = None) -> None:
    thread_id = mail["thread_id"]
    session = None if board.knows(thread_id) else api.find(thread_id)
    carrier_emails = {c["email"].lower() for c in carriers}
    kind = route(mail, carrier_emails, board.knows(thread_id) or session is not None)
    print(f"{kind:17} #{mail['id']} {mail['from']}: {mail['subject']}")
    if kind == "rfq" and max_rfq_age is not None and time.time() - sent_at(mail) > max_rfq_age:
        print(f"expired RFQ skipped #{mail['id']}: older than {max_rfq_age:.0f} s, it can't score")  # e.g. backlog
        return
    if kind == "rfq":
        # Bids arrive over a minute or more, so every RFQ waits in its own thread.
        _start(handle_rfq, mail, box, api, board, carriers)
    elif kind == "carrier_bid" and not board.deliver(mail):
        print(f"late bid ignored: {mail['from']}")
    elif kind == "customer_reply" and session and session.get("stage") == "pricing" \
            and (session.get("rfq") or {}).get("awaiting") == "pickup":
        _start(resume_after_pickup, mail, box, api, board, carriers, session)  # the answer to our pickup question
    elif kind == "customer_reply":
        _start(handle_customer_reply, mail, box, api, session)
    elif kind == "tracking":
        _start(handle_tracking, mail, box, api)
    elif kind == "booking_confirmed":
        handle_booking_confirmed(mail, box, api)
    elif kind == "tariff":
        _start(_forward_tariff, mail, box, api)
    # ratedesk answers: handled together with the portal client (B4)


def _forward_tariff(mail: dict, box, api) -> None:
    """Airlines mail their monthly tariffs: hand every attachment to the backend's tariff ingestion."""
    for attachment in mail["attachments"]:
        try:  # one unreadable file must not stop the airline's other attachments
            content = base64.b64encode(box.attachment(mail, attachment)).decode()
            result = api.ingest_tariff(attachment["filename"], content, mail["from"])
        except Exception as error:
            result = f"failed: {type(error).__name__}: {error}"
        print(f"tariff {attachment['filename']} from {mail['from']}: {result}")


def _start(handler, *args) -> None:
    threading.Thread(target=handler, args=args, daemon=True).start()


if __name__ == "__main__":
    main()
