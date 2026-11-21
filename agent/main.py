"""Worker: polls the mailbox, routes every mail and hands it to an agent, one thread per RFQ."""

import os
import threading
import time

from backend import Backend
from bids import BidBoard
from booking_agent import handle_booking_confirmed, handle_customer_reply
from carriers import load_carriers
from inbox import FixtureMailbox
from rfq_agent import handle_rfq
from router import route
from tracking_agent import handle_tracking

POLL_SECONDS = 5


def main() -> None:
    box = FixtureMailbox(os.environ.get("FIXTURE_INBOX", "fixtures/inbox"))
    api = Backend()
    board = BidBoard()
    carriers = load_carriers(os.environ.get("CARRIERS_FILE", "fixtures/carriers.json"))
    carrier_emails = {c["email"].lower() for c in carriers}
    print(f"worker running, {len(carriers)} carriers")
    while True:
        for mail in box.fetch():
            thread_id = mail["thread_id"]
            session = None if board.knows(thread_id) else api.find(thread_id)
            kind = route(mail, carrier_emails, board.knows(thread_id) or session is not None)
            print(f"{kind:17} {mail['from']}: {mail['subject']}")
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
            # tariff → backend ingestion (B3), ratedesk → rate desk answers (with B4)
        time.sleep(POLL_SECONDS)


def _start(handler, *args) -> None:
    threading.Thread(target=handler, args=args, daemon=True).start()


if __name__ == "__main__":
    main()
