"""Worker: polls the mailbox, routes every mail and hands it to an agent, one thread per RFQ."""

import os
import threading
import time

from backend import Backend
from bids import BidBoard
from carriers import load_carriers
from inbox import FixtureMailbox
from rfq_agent import handle_rfq
from router import route

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
            kind = route(mail, carrier_emails, board.knows(thread_id) or api.find(thread_id) is not None)
            print(f"{kind:15} {mail['from']}: {mail['subject']}")
            if kind == "rfq":
                # Bids arrive over a minute or more, so every RFQ waits in its own thread.
                threading.Thread(target=handle_rfq, args=(mail, box, api, board, carriers), daemon=True).start()
            elif kind == "carrier_bid" and not board.deliver(mail):
                print(f"late bid ignored: {mail['from']}")
            # customer_reply → A5 booking, tracking → A6, tariff → backend ingestion (B3)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
