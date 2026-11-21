"""Worker: polls the mailbox, routes every mail and hands it to an agent, one thread per session."""

import os
import threading
import time

from backend import Backend
from inbox import FixtureMailbox
from rfq_agent import handle_rfq
from router import route

POLL_SECONDS = 5


def main() -> None:
    box = FixtureMailbox(os.environ.get("FIXTURE_INBOX", "fixtures/inbox"))
    api = Backend()
    carriers: set[str] = set()  # shortcut: empty until the start-kit carrier list arrives (U1)
    print("worker running")
    while True:
        for mail in box.fetch():
            kind = route(mail, carriers, api.find(mail["thread_id"]) is not None)
            print(f"{kind:15} {mail['from']}: {mail['subject']}")
            if kind == "rfq":
                # Bids arrive over minutes (A4), so every RFQ gets its own thread.
                threading.Thread(target=handle_rfq, args=(mail, box, api), daemon=True).start()
            # customer_reply → A5 booking, tracking → A6, carrier_bid → A4, tariff → backend ingestion
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
