"""Worker: polls the mailbox, routes every mail and hands it to an agent in its own thread.

Run live:   uv run --env-file ../.env python main.py          (needs FIVEU_API_KEY and the backend on BACKEND_URL)
Run local:  MOCK=1 uv run --env-file ../.env python main.py   (mails from fixtures/inbox, nothing is sent; the
            LLM still needs the key, and sessions go to BACKEND_URL, so point it at a local backend)
"""

import base64
import os
import threading
import time

from backend import Backend
from bids import BidBoard
from booking_agent import handle_booking_confirmed, handle_customer_reply
from carriers import load_carriers
from inbox import FiveUMailbox, FixtureMailbox
from rfq_agent import handle_rfq
from router import route
from tracking_agent import handle_tracking

POLL_SECONDS = 1.5  # 5U: "response time counts: poll every second or two"
RETRY_SECONDS = 300  # an RFQ expires 6 min after it was sent: retry a failed dispatch until then, then give up


def main() -> None:
    live = os.environ.get("FIVEU_API_KEY") and os.environ.get("MOCK") != "1"
    box = FiveUMailbox() if live else FixtureMailbox(os.environ.get("FIXTURE_INBOX", "fixtures/inbox"))
    api = Backend()
    board = BidBoard()
    carriers = load_carriers(os.environ.get("CARRIERS_FILE", "fixtures/carriers.json"))
    print(f"worker running ({'live 5U mailbox' if live else 'fixtures'}), {len(carriers)} carriers")
    failed: dict = {}
    while True:
        poll_once(box, api, board, carriers, failed)
        time.sleep(POLL_SECONDS)


def poll_once(box, api, board: BidBoard, carriers: list[dict], failed: dict) -> None:
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
            dispatch(mail, box, api, board, carriers)
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


def dispatch(mail: dict, box, api, board: BidBoard, carriers: list[dict]) -> None:
    thread_id = mail["thread_id"]
    session = None if board.knows(thread_id) else api.find(thread_id)
    carrier_emails = {c["email"].lower() for c in carriers}
    kind = route(mail, carrier_emails, board.knows(thread_id) or session is not None)
    print(f"{kind:17} #{mail['id']} {mail['from']}: {mail['subject']}")
    if kind == "rfq":
        # Bids arrive over a minute or more, so every RFQ waits in its own thread.
        _start(handle_rfq, mail, box, api, board, carriers)
    elif kind == "carrier_bid" and not board.deliver(mail):
        print(f"late bid ignored: {mail['from']}")
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
        content = base64.b64encode(box.attachment(mail, attachment)).decode()
        result = api.ingest_tariff(attachment["filename"], content, mail["from"])
        print(f"tariff {attachment['filename']} from {mail['from']}: {result}")


def _start(handler, *args) -> None:
    threading.Thread(target=handler, args=args, daemon=True).start()


if __name__ == "__main__":
    main()
