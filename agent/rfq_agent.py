"""RFQ agent: extract → ask carriers → collect bids until the cut-off → price → quote in the customer's thread."""

import os
import queue
import time
from datetime import datetime

from backend import now
from bids import BidBoard, read_bid
from carriers import carriers_for
from extract import extract, to_rfq
from templates import bid_request_text, quote_text

# Full time points end 2 min after the request; leave room for pricing and sending.
BID_CUTOFF_SECONDS = float(os.environ.get("BID_CUTOFF_SECONDS", "90"))


def handle_rfq(mail: dict, box, api, board: BidBoard | None = None, carriers: list[dict] | tuple = (),
               cutoff_s: float = BID_CUTOFF_SECONDS) -> None:
    session_id = api.create_session(mail["from"], mail["thread_id"])
    api.event(session_id, "mail_in", f"RFQ from {mail['from']}: {mail['subject']}")
    api.event(session_id, "routed", "New RFQ (rules, no LLM)")
    try:
        raw, cost = extract(mail)
        rfq, missing = to_rfq(raw)
        api.update(session_id, stage="pricing", rfq=rfq, llm_cost_usd=cost)
        api.event(session_id, "extracted", f"{rfq['origin']} → {rfq['destination']}, {rfq['ask']}", rfq, cost)
        if missing:
            return hand_over(api, session_id, f"Can't price yet, missing: {', '.join(missing)}")

        bids, bid_cost = _carrier_round(session_id, mail, rfq, carriers_for(carriers, rfq), box, api, board, cutoff_s)
        if bids or bid_cost:
            api.update(session_id, bids=bids, llm_cost_usd=cost + bid_cost)

        result = api.price(rfq, bids)
        chosen = result["chosen"]
        api.event(session_id, "priced", f"{len(result['options'])} options. {result.get('why', '')}".strip(), result)
        if not chosen:
            return hand_over(api, session_id, "No price found for this request")

        if api.session(session_id).get("paused"):
            return  # a person took over in the Sessions UI
        box.reply(mail, quote_text(rfq, chosen))
        api.update(session_id, stage="quoted", quote={**chosen, "sent_at": now()})
        api.event(session_id, "quote_sent",
                  f"Quote sent: {chosen['currency']} {chosen['total']:,.2f} all-in ({rfq['ask']})", chosen)
    except Exception as error:  # one broken mail must not stop the worker; the session shows what happened
        api.update(session_id, stage="failed", needs_human=True)
        api.event(session_id, "error", f"{type(error).__name__}: {error}")


def _carrier_round(session_id, mail, rfq, targets, box, api, board, cutoff_s) -> tuple[list[dict], float]:
    """Mails every target, then collects replies until all answered or the cut-off. Returns (bids, LLM cost)."""
    if not targets:
        return [], 0.0
    replies: queue.Queue = queue.Queue()
    threads = []
    for carrier in targets:
        thread_id = box.send(carrier["email"], f"Rate request {rfq['origin']}-{rfq['destination']}",
                             bid_request_text(rfq, carrier["kind"]))
        board.watch(thread_id, replies, carrier)
        threads.append(thread_id)
    api.event(session_id, "carrier_asked", f"Asked {len(targets)}: {', '.join(c['name'] for c in targets)}")

    deadline = _received_at(mail) + cutoff_s
    bids, cost, answered = [], 0.0, 0
    try:
        while answered < len(targets) and (left := deadline - time.time()) > 0:
            try:
                carrier, reply = replies.get(timeout=left)
            except queue.Empty:
                break
            answered += 1
            bid, bid_cost = read_bid(reply["body"])
            cost += bid_cost
            if bid is None:
                api.event(session_id, "bid", f"{carrier['name']}: no usable offer", cost=bid_cost)
                continue
            option = {"source": "carrier_bid", "leg": "pickup" if carrier["kind"] == "trucker" else "air",
                      "carrier": carrier["name"], "rate_id": bid["rate_id"], "currency": bid["currency"],
                      "total": bid["total"], "transit_days": bid["transit_days"]}
            bids.append(option)
            transit = f", {option['transit_days']:g} days" if option["transit_days"] is not None else ""
            api.event(session_id, "bid", f"{carrier['name']}: {option['currency']} {option['total']:,.2f}{transit}",
                      option, bid_cost)
    finally:
        board.forget(threads)  # late replies are no longer waited for
    if answered < len(targets):
        api.event(session_id, "bid", f"Cut-off: {answered} of {len(targets)} answered in time")
    return bids, cost


def _received_at(mail: dict) -> float:
    """When 5U sent the RFQ: the response-time score counts from there."""
    try:
        return datetime.fromisoformat(mail["received_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return time.time()


def hand_over(api, session_id: int, reason: str) -> None:
    api.update(session_id, needs_human=True)
    api.event(session_id, "needs_human", reason)
