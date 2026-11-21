"""RFQ agent: extract → ask carriers → collect bids until the cut-off → price → quote in the customer's thread."""

import base64
import os
import queue
import time
from datetime import datetime

from attachments import dangerous_goods
from backend import now
from bids import BidBoard, read_bid
from carriers import carriers_for
from dg import attachment_totals, dg_info
from extract import read_request
from inbox import mail_data, reply_data
from templates import bid_request_text, quote_text, signature_name

# Full time points end 2 min after the request; leave room for pricing and sending.
BID_CUTOFF_SECONDS = float(os.environ.get("BID_CUTOFF_SECONDS", "90"))
# A handed-over RFQ that no person answers by then gets a best-effort quote (a rejected answer scores 0, like none)
FALLBACK_AT_SECONDS = float(os.environ.get("FALLBACK_AT_SECONDS", "100"))
# Door-to-port can't be priced without a trucker: past the cut-off, keep waiting for the FIRST pickup bid up to here.
# A quote at 4:30 still earns accuracy + cost points; no quote earns nothing (docs/GO_LIVE.md 2.1).
PICKUP_DEADLINE_SECONDS = float(os.environ.get("PICKUP_DEADLINE_SECONDS", "270"))


def handle_rfq(mail: dict, box, api, board: BidBoard | None = None, carriers: list[dict] | tuple = (),
               cutoff_s: float = BID_CUTOFF_SECONDS) -> None:
    session_id = api.create_session(mail["from"], mail["thread_id"], mail.get("received_at"))
    api.event(session_id, "mail_in", f"RFQ from {mail['from']}: {mail['subject']}", mail_data(mail))
    api.event(session_id, "routed", "New RFQ (rules, no LLM)")
    try:
        read = read_request(mail)
        rfq, missing, cost = read["rfq"], read["missing"], read["cost"]
        rfq["contact_name"] = signature_name(mail["body"])  # "Hi Anna," in every mail to this customer
        if dg := dangerous_goods(mail, box):  # the packing list wins over "non-dangerous" in the mail
            rfq["dangerous_goods"], rfq["dg_declared"] = True, dg
            api.event(session_id, "extracted", f"Dangerous goods in the attachment: {dg}")
        attachments = _attachment_texts(mail, box, api)  # all formats incl. PDF (round 11's SLI was a PDF)
        if not rfq.get("dangerous_goods") and (info := dg_info(mail["body"], *attachments)):
            rfq["dangerous_goods"], rfq["dg_declared"] = True, info
            api.event(session_id, "extracted", f"Dangerous goods found: {info}")
        for note in _use_packing_list_totals(rfq, attachments):
            api.event(session_id, "routed", note)
        missing = [m for m in missing if not (m == "dimensions or volume" and rfq.get("volume_m3"))]
        if missing == ["dimensions or volume"]:  # no answer scores 0: price on the actual weight instead
            missing = []
            api.event(session_id, "routed", "No dimensions or volume given: priced on the actual weight")
        api.update(session_id, stage="pricing", rfq=rfq, llm_cost_usd=cost)
        escalated = f" (re-read by {read['model']}: {'; '.join(read['escalated'])})" if read["escalated"] else ""
        api.event(session_id, "extracted", f"{rfq['origin']} → {rfq['destination']}, {rfq['ask']}{escalated}", rfq, cost)
        if missing:
            return hand_over(api, session_id, f"Can't price yet, missing: {', '.join(missing)}")

        bids, bid_cost = _carrier_round(session_id, mail, rfq, carriers_for(carriers, rfq), box, api, board, cutoff_s)
        if bids or bid_cost:
            api.update(session_id, bids=bids, llm_cost_usd=cost + bid_cost)

        result = api.price(rfq, bids)
        chosen = result["chosen"]
        api.event(session_id, "priced", f"{len(result['options'])} options. {result.get('why', '')}".strip(), result)
        if not chosen:
            hand_over(api, session_id, "No price found for this request")
            return _fallback_quote(session_id, mail, rfq, bids, box, api)

        if api.session(session_id).get("paused"):
            return  # a person took over in the Sessions UI
        text = quote_text(rfq, chosen)
        box.reply(mail, text)
        api.update(session_id, stage="quoted", quote={**chosen, "sent_at": now()})
        api.event(session_id, "quote_sent",
                  f"Quote sent: {chosen['currency']} {chosen['total']:,.2f} all-in ({rfq['ask']})",
                  {**reply_data(mail, text), "option": chosen})
    except Exception as error:  # one broken mail must not stop the worker; the session shows what happened
        api.update(session_id, stage="failed", needs_human=True)
        api.event(session_id, "error", f"{type(error).__name__}: {error}")


def _carrier_round(session_id, mail, rfq, targets, box, api, board, cutoff_s) -> tuple[list[dict], float]:
    """Mails every target, then collects replies until all answered or the cut-off. Returns (bids, LLM cost)."""
    if not targets:
        return [], 0.0
    replies: queue.Queue = queue.Queue()
    threads, asked, unreachable = [], [], []
    for carrier in targets:
        try:  # one address 5U refuses (422) or a send hiccup must not kill the RFQ: skip that carrier
            thread_id = box.send(carrier["email"], f"Rate request {rfq['origin']}-{rfq['destination']}",
                                 bid_request_text(rfq, carrier["kind"]))
        except Exception as error:
            unreachable.append(f"{carrier['name']} ({type(error).__name__})")
            continue
        board.watch(thread_id, replies, carrier)
        threads.append(thread_id)
        asked.append(carrier)
    not_sent = f"; not sent: {', '.join(unreachable)}" if unreachable else ""
    api.event(session_id, "carrier_asked", f"Asked {len(asked)}: {', '.join(c['name'] for c in asked)}{not_sent}")
    targets = asked
    if not targets:
        return [], 0.0

    cutoff = sent_at(mail) + cutoff_s
    pickup_deadline = sent_at(mail) + max(cutoff_s, PICKUP_DEADLINE_SECONDS)
    need_pickup = bool(rfq.get("pickup")) and any(c["kind"] == "trucker" for c in targets)
    bids, cost, answered = [], 0.0, 0
    try:
        while answered < len(targets):
            got_pickup = any(b["leg"] == "pickup" for b in bids)
            if (left := (pickup_deadline if need_pickup and not got_pickup else cutoff) - time.time()) <= 0:
                break
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


def sent_at(mail: dict) -> float:
    """When 5U sent the RFQ: the response-time score counts from there."""
    try:
        return datetime.fromisoformat(mail["received_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return time.time()


def hand_over(api, session_id: int, reason: str) -> None:
    api.update(session_id, needs_human=True)
    api.event(session_id, "needs_human", reason)


def _attachment_texts(mail: dict, box, api) -> list[str]:
    """Text of the RFQ's attachments (packing list, SLI) in every format the backend reads, PDF included."""
    texts = []
    for attachment in (mail.get("attachments") or [])[:5]:
        try:
            content = base64.b64encode(box.attachment(mail, attachment)).decode()
            texts.append(api.attachment_text(attachment.get("filename", ""), content))
        except Exception as error:  # a missing attachment must never cost the quote
            print(f"attachment {attachment.get('filename')} not read: {type(error).__name__}: {error}")
    return texts


def _use_packing_list_totals(rfq: dict, attachments: list[str]) -> list[str]:
    """A packing list's stated totals beat the mail (5U hides traps in attachments). Returns what was changed."""
    notes = []
    for text in attachments:
        kg, cbm = attachment_totals(text)
        pieces = rfq.get("pieces") or []
        mail_kg = sum((p.get("count") or 1) * (p.get("weight_kg") or 0) for p in pieces)
        if kg and mail_kg and abs(kg - mail_kg) > max(1.0, 0.01 * kg):
            for p in pieces:
                p["weight_kg"] = (p.get("weight_kg") or 0) * kg / mail_kg
            notes.append(f"Packing list says {kg:g} kg, the mail {mail_kg:g} kg: using the packing list")
        if cbm and abs(cbm - (rfq.get("volume_m3") or 0)) > 0.01 * cbm:
            notes.append(f"Packing list says {cbm:g} cbm (mail: {rfq.get('volume_m3')}): using the packing list")
            rfq["volume_m3"] = cbm
            for p in pieces:  # the stated total volume wins over dimensions from the mail
                p["length_cm"] = p["width_cm"] = p["height_cm"] = None
    return notes


def _fallback_quote(session_id: int, mail: dict, rfq: dict, bids: list[dict], box, api) -> None:
    """At ~T+1:40, if nobody stepped in: price with earlier trucker bids for the zone and send that quote."""
    wait = sent_at(mail) + FALLBACK_AT_SECONDS - time.time()
    if wait > 0:
        time.sleep(wait)
    session = api.session(session_id)
    if session.get("paused") or session.get("quote") or not session.get("needs_human"):
        return  # a person took over or answered
    result = api.price(rfq, bids, fallback=True)
    chosen = result.get("chosen")
    if not chosen:
        return api.event(session_id, "needs_human", "Fallback: still no price, a person has to answer")
    if api.session(session_id).get("paused"):
        return
    text = quote_text(rfq, chosen)
    box.reply(mail, text)
    api.update(session_id, stage="quoted", needs_human=False, quote={**chosen, "sent_at": now(), "fallback": True})
    api.event(session_id, "quote_sent",
              f"Fallback quote sent: {chosen['currency']} {chosen['total']:,.2f} all-in ({result.get('why', '')[:120]})",
              {**reply_data(mail, text), "option": chosen})
