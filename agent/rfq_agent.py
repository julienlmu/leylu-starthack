"""RFQ agent: extract → ask carriers → collect bids until the cut-off → price → quote in the customer's thread."""

import base64
import os
import re
import queue
import threading
import time
from datetime import datetime

import amendments
import constraints
import exclusions
import gate
from airports import aliased
from attachments import dangerous_goods
from backend import now
import bids as bids_mod
from bids import BidBoard, info_request, read_bid
from carriers import carriers_for
from dg import attachment_totals, dg_info
from extract import doubts, city_zone, read_request, totals, zone_airport
from inbox import latest_text, mail_data, reply_data
from templates import bid_request_text, pickup_question_text, info_reply_text, quote_text, signature_name

# Full time points end 2 min after the request; leave room for pricing and sending.
BID_CUTOFF_SECONDS = float(os.environ.get("BID_CUTOFF_SECONDS", "90"))
# "including truck pickup from our warehouse" with no address: the reader leaves pickup empty, but it is door-to-port.
# Not "ready for pickup on <date>": every RFQ says that.
DOOR_PICKUP = re.compile(r"\btruck(ing)?\s+(pick[- ]?up|collection)\b|\b(pick[- ]?up|collection)\s+(from|at)\s+(our|the)\s"
                         r"|\bfrom our (warehouse|site|plant|factory|premises|facility)\b"
                         r"|\babholung\s+(bei|ab|von|in)\s+(uns|unserem|unserer)\b|\bab (unserem|unserer) (lager|werk|halle)\b",
                         re.I)
# A handed-over RFQ that no person answers by then gets a best-effort quote (a rejected answer scores 0, like none)
FALLBACK_AT_SECONDS = float(os.environ.get("FALLBACK_AT_SECONDS", "100"))
# Off switches for the newer fallbacks (env + restart, no deploy): "off" restores the hand-over to a person.
DENSITY_HOLD = os.environ.get("DENSITY_HOLD", "on") != "off"  # odd numbers: quoted as read at FALLBACK_AT_SECONDS
CRASH_FALLBACK = os.environ.get("CRASH_FALLBACK", "on") != "off"  # an error after reading: the fallback quote
# Door-to-port can't be priced without a trucker: past the cut-off, keep waiting for the FIRST pickup bid up to here.
# A quote at 4:30 still earns accuracy + cost points; no quote earns nothing (docs/GO_LIVE.md 2.1).
PICKUP_DEADLINE_SECONDS = float(os.environ.get("PICKUP_DEADLINE_SECONDS", "270"))
# A quote the gate holds goes out on its own at this time after the RFQ unless a person pauses or replies first:
# a late quote still earns accuracy and cost points, no quote earns nothing.
GATE_AUTO_SEND_SECONDS = float(os.environ.get("GATE_AUTO_SEND_SECONDS", "240"))
_sleep = time.sleep  # tests replace it


def handle_rfq(mail: dict, box, api, board: BidBoard | None = None, carriers: list[dict] | tuple = (),
               cutoff_s: float = BID_CUTOFF_SECONDS, session_id: int | None = None) -> None:
    """session_id: continue that session (an RFQ resumed after a restart) instead of opening a new one."""
    resumed = session_id is not None  # never ask the customer a second time after a restart
    if session_id is None:
        session_id = api.create_session(mail["from"], mail["thread_id"], mail.get("received_at"))
        api.event(session_id, "mail_in", f"RFQ from {mail['from']}: {mail['subject']}", mail_data(mail))
        api.event(session_id, "routed", "New RFQ (rules, no LLM)")
    else:
        api.event(session_id, "routed", "Resumed after a restart: priced and quoted again from the start")
    try:
        read = read_request(mail)
        rfq, missing, cost = read["rfq"], read["missing"], read["cost"]
        rfq["contact_name"] = signature_name(mail["body"])  # "Hi Anna," in every mail to this customer
        if constraints.ON:  # excluded / required carriers, max transit, routing wishes (rules, no LLM)
            found = constraints.read(f"{mail['subject']}\n{mail['body']}", carriers)
            if found["remember"]:
                exclusions.remember(mail["from"], found["remember"])  # "… or for any of our future inquiries"
            for line in constraints.apply(rfq, found, exclusions.known(mail["from"])):
                api.event(session_id, "extracted", line)
        else:
            airlines = [c["name"] for c in carriers if c.get("kind") == "airline"]
            if said := exclusions.excluded_in(f"{mail['subject']}\n{mail['body']}", airlines):
                exclusions.remember(mail["from"], said)  # "… or for any of our future inquiries"
            if excluded := exclusions.known(mail["from"]):
                rfq["excluded_airlines"] = excluded  # priced without them (backend) and not asked for bids
                api.event(session_id, "extracted", f"Customer excluded: {', '.join(excluded)}")
        if dg := dangerous_goods(mail, box):  # the packing list wins over "non-dangerous" in the mail
            rfq["dangerous_goods"], rfq["dg_declared"] = True, dg
            api.event(session_id, "extracted", f"Dangerous goods in the attachment: {dg}")
        attachments = _attachment_texts(session_id, mail, box, api)  # all formats incl. PDF (round 11's SLI was a PDF)
        if not rfq.get("dangerous_goods") and (info := dg_info(mail["body"], *attachments)):
            rfq["dangerous_goods"], rfq["dg_declared"] = True, info
            api.event(session_id, "extracted", f"Dangerous goods found: {info}")
        notes = _use_packing_list_totals(rfq, attachments)
        for note in notes:
            api.event(session_id, "routed", note)
        if notes:  # the packing list changed weight or volume: check the density again
            missing = [m for m in missing if not m.startswith("implausible density")]
            missing += [d for d in doubts(rfq) if d.startswith("implausible density")]
        missing = [m for m in missing if not (m == "dimensions or volume" and rfq.get("volume_m3"))]
        if any(n.startswith("No weight in the mail") for n in notes):
            missing = [m for m in missing if m != "weight"]
        if missing == ["dimensions or volume"]:  # no answer scores 0: price on the actual weight instead
            missing = []
            api.event(session_id, "routed", "No dimensions or volume given: priced on the actual weight")
        api.update(session_id, stage="pricing", rfq=rfq, llm_cost_usd=cost)
        escalated = f" (re-read by {read['model']}: {'; '.join(read['escalated'])})" if read["escalated"] else ""
        airports = f" ({rfq['airport_note']})" if rfq.get("airport_note") else ""
        api.event(session_id, "extracted", f"{rfq['origin']} → {rfq['destination']}, {rfq['ask']}{airports}{escalated}",
                  rfq, cost)
        odd = [m for m in missing if m.startswith("implausible density")]
        doubt = bool(DENSITY_HOLD and missing and len(odd) == len(missing))
        if doubt:  # numbers that look odd may still be right: a 5U trap or a misread. A person gets until the fallback
            missing = []  # time to correct them, then they are quoted as read
            hand_over(api, session_id, f"Check the numbers ({'; '.join(odd)}): quoted as read at "
                                       f"{FALLBACK_AT_SECONDS:.0f} s unless a person steps in")
        if missing == ["origin"] and rfq.get("pickup") is None and DOOR_PICKUP.search(latest_text(mail["body"])):
            rfq["pickup"] = {"address": "customer warehouse (address not given)", "zone": None}  # rounds 16, 17
        if missing == ["origin"] and rfq.get("pickup") is not None and not resumed:  # door-to-port, from where?
            return _ask_for_pickup(session_id, mail, rfq, box, api)
        if missing:
            return hand_over(api, session_id, f"Can't price yet, missing: {', '.join(missing)}")

        _price_and_quote(session_id, mail, rfq, cost, box, api, board, carriers, cutoff_s, attachments, doubt)
    except Exception as error:  # one broken mail must not stop the worker; the session shows what happened
        api.update(session_id, stage="failed", needs_human=True)
        api.event(session_id, "error", f"{type(error).__name__}: {error}")


def fallback_after_restart(session: dict, mail: dict, box, api) -> None:
    """A handed-over RFQ whose fallback timer died with the worker: run the fallback now (it waits for its time).
    Only for a reading that can be priced: one handed over for a missing origin, destination or weight stays with a person."""
    rfq = session.get("rfq") or {}
    if not (rfq.get("origin") and rfq.get("destination") and rfq.get("pieces")
            and all(p.get("weight_kg") for p in rfq["pieces"])):
        return
    try:
        _fallback_quote(session["id"], mail, session["rfq"], session.get("bids") or [], box, api)
    except Exception as error:
        api.event(session["id"], "error", f"Fallback after a restart failed: {type(error).__name__}: {error}")


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
    bids, cost, answered, informed = [], 0.0, set(), set()
    chargeable = chargeable_kg(rfq)
    try:
        while len(answered) < len(targets):  # distinct carriers: a revised bid is no second carrier
            got_pickup = any(b["leg"] == "pickup" for b in bids)
            if (left := (pickup_deadline if need_pickup and not got_pickup else cutoff) - time.time()) <= 0:
                break
            try:
                carrier, reply = replies.get(timeout=left)
            except queue.Empty:
                break
            if carrier["email"] not in informed and (asks := info_request(reply["body"])):
                informed.add(carrier["email"])  # answer once, then keep waiting for this carrier's real bid
                try:
                    box.reply(reply, info_reply_text(rfq, asks))
                    api.event(session_id, "bid", f"{carrier['name']} asked for {', '.join(asks)}: answered")
                except Exception as error:
                    api.event(session_id, "bid", f"{carrier['name']} asked for {', '.join(asks)}: not answered ({error})")
                continue
            answered.add(carrier["email"])
            bid, bid_cost = read_bid(reply["body"], chargeable)
            cost += bid_cost
            if bid is None:
                api.event(session_id, "bid", f"{carrier['name']}: no usable offer", cost=bid_cost)
                continue
            if bid["total"] is not None and (floor := bid_floor(carrier["kind"], chargeable)) and bid["total"] < floor:
                api.event(session_id, "bid", f"{carrier['name']}: {bid['currency']} {bid['total']:,.2f} is below "
                          f"{floor:,.0f} for {chargeable or 0:,.0f} kg (a per-kg rate read as the total?): not used",
                          bid, bid_cost)
                continue
            option = {"source": "carrier_bid", "leg": "pickup" if carrier["kind"] == "trucker" else "air",
                      "carrier": carrier["name"], "rate_id": bid["rate_id"], "currency": bid["currency"],
                      "total": bid["total"], "transit_days": bid["transit_days"]}
            bids = [b for b in bids if b["carrier"] != carrier["name"]] + [option]  # the latest bid replaces its first
            transit = f", {option['transit_days']:g} days" if option["transit_days"] is not None else ""
            api.event(session_id, "bid", f"{carrier['name']}: {option['currency']} {option['total']:,.2f}{transit}",
                      option, bid_cost)
    finally:
        board.forget(threads)  # late replies are no longer waited for
    if len(answered) < len(targets):
        api.event(session_id, "bid", f"Cut-off: {len(answered)} of {len(targets)} answered in time")
    return bids, cost


CBM_KG = 167  # the kit's volume weight: 1 cbm = 167 kg
# Below these an offer is not a real all-in price (kit rates are > 1 EUR/kg all-in, truckers > 50 EUR): most likely a
# per-kg rate read as the total. Used as the cheapest bid, it gets the quote rejected too_low.
AIR_FLOOR_PER_KG = float(os.environ.get("BID_FLOOR_EUR_PER_KG", "0.3"))
AIR_FLOOR_MIN = 25.0
PICKUP_FLOOR = 20.0


def chargeable_kg(rfq: dict) -> float | None:
    """The billed weight: max(actual kg, cbm × 167), or None when the request gives neither."""
    try:
        kg, m3 = totals(rfq)
    except (KeyError, TypeError):
        return None
    if not kg and not m3:
        return None
    return round(max(kg or 0.0, (m3 or 0.0) * CBM_KG), 2)


def bid_floor(kind: str, chargeable: float | None) -> float:
    if not bids_mod.BID_SHAPES:
        return 0.0  # BID_SHAPES=off: every bid is used as before
    if kind == "trucker":
        return PICKUP_FLOOR
    return max(AIR_FLOOR_MIN, AIR_FLOOR_PER_KG * (chargeable or 0.0))


def sent_at(mail: dict) -> float:
    """When 5U sent the RFQ: the response-time score counts from there."""
    try:
        return datetime.fromisoformat(mail["received_at"]).timestamp()
    except (KeyError, TypeError, ValueError):
        return time.time()


def hand_over(api, session_id: int, reason: str) -> None:
    api.update(session_id, needs_human=True)
    api.event(session_id, "needs_human", reason)


def _attachment_texts(session_id, mail: dict, box, api) -> list[str]:
    """Text of the RFQ's attachments (packing list, SLI) in every format the backend reads, PDF included."""
    texts = []
    for attachment in (mail.get("attachments") or [])[:5]:
        try:
            content = base64.b64encode(box.attachment(mail, attachment)).decode()
            texts.append(text := api.attachment_text(attachment.get("filename", ""), content))
            if not (text or "").strip():  # image scan, old .xls, ...: never skip it silently
                api.event(session_id, "extracted", f"Attachment {attachment.get('filename')} has no readable text: "
                          "DG and totals in it are not checked")
        except Exception as error:  # a missing attachment must never cost the quote
            print(f"attachment {attachment.get('filename')} not read: {type(error).__name__}: {error}")
    return texts


def _use_packing_list_totals(rfq: dict, attachments: list[str]) -> list[str]:
    """A packing list's stated totals beat the mail (5U hides traps in attachments). Returns what was changed."""
    notes = []
    # one packing list per lot: the stated totals add up over all attachments before they are compared with the mail
    # shortcut: identical totals count once (packing list + SLI of the same goods); two lots with equal kg AND cbm
    # would be undercounted, upgrade if 5U sends such lots
    stated = dict.fromkeys(attachment_totals(text) for text in attachments)
    kg = sum(k for k, _ in stated if k) or None
    cbm = sum(c for _, c in stated if c) or None
    if kg or cbm:
        pieces = rfq.get("pieces") or []
        mail_kg = sum((p.get("count") or 1) * (p.get("weight_kg") or 0) for p in pieces)
        if kg and not mail_kg:  # the mail gives no weight at all: the packing list's total is the only one
            if not pieces:
                rfq["pieces"] = pieces = [{"count": 1, "length_cm": None, "width_cm": None, "height_cm": None}]
            count = sum(p.get("count") or 1 for p in pieces)
            for p in pieces:
                p["weight_kg"] = kg / count
            notes.append(f"No weight in the mail: using the packing list's {kg:g} kg")
        elif kg and mail_kg and abs(kg - mail_kg) > max(1.0, 0.01 * kg):
            for p in pieces:
                p["weight_kg"] = (p.get("weight_kg") or 0) * kg / mail_kg
            notes.append(f"Packing list says {kg:g} kg, the mail {mail_kg:g} kg: using the packing list")
        if cbm and abs(cbm - (rfq.get("volume_m3") or 0)) > 0.01 * cbm:
            notes.append(f"Packing list says {cbm:g} cbm (mail: {rfq.get('volume_m3')}): using the packing list")
            rfq["volume_m3"] = cbm
            for p in pieces:  # the stated total volume wins over dimensions from the mail
                p["length_cm"] = p["width_cm"] = p["height_cm"] = None
    return notes


def _gate(session_id, mail, rfq, result, attachments, api) -> tuple[str, dict, bool]:
    """Quote gate (gate.py): (mail text, option to quote, hold?). Fails open: a gate error never costs the quote."""
    try:
        verdict = gate.review(rfq, result, mail, attachments, time.time() - sent_at(mail))
        text, more = gate.finish(quote_text(rfq, verdict["chosen"], mail.get("body")), verdict, rfq)
    except Exception as error:
        api.event(session_id, "error", f"Quote gate skipped: {type(error).__name__}: {error}")
        return quote_text(rfq, result["chosen"], mail.get("body")), result["chosen"], False
    findings = verdict["findings"] + more
    if findings:
        api.event(session_id, "routed", f"Quote gate: {gate.summary(findings)}", {"findings": findings})
    if rfq.get("dangerous_goods"):
        api.update(session_id, rfq=rfq)  # the gate may have found DG the other checks missed
    hold = gate.MODE == "enforce" and (verdict["hold"] or any(f["level"] == "hold" for f in more))
    return text, verdict["chosen"], hold


def _hold(session_id, mail, api) -> bool:
    """Dead man's switch for a held quote. True = nobody stepped in by the auto-send time, send it now;
    False = a person paused the session or quoted from the Sessions UI."""
    send_at = max(sent_at(mail) + GATE_AUTO_SEND_SECONDS, time.time())
    api.update(session_id, needs_human=True)  # the backend pushes needs_human to ntfy
    api.event(session_id, "needs_human", f"Quote held by the gate: it sends itself in {send_at - time.time():.0f} s "
                                         "unless a person pauses or replies in the Sessions UI")
    while time.time() < send_at:
        try:
            current = api.session(session_id)
        except Exception:  # a backend hiccup (e.g. a restart) must not cost the held quote
            current = {}
        if current.get("paused") or current.get("quote"):  # paused, or a person quoted by hand
            return False
        _sleep(min(3.0, max(0.0, send_at - time.time())))
    api.update(session_id, needs_human=False)
    api.event(session_id, "routed", "Nobody stepped in: the held quote goes out")
    return True


def _reread(session_id, mail, later, rfq, bids, api, result) -> tuple[dict, dict, float]:
    """Reads the request again with the customer's later mails on top (one more extraction), then prices again.
    A reading that comes back incomplete keeps the first one."""
    newest = "\n\n".join(latest_text(m["body"]) for m in reversed(later))
    merged = {**mail, "body": f"{newest}\n\n(Earlier mail, corrected by the lines above:)\n{mail['body']}"}
    api.event(session_id, "mail_in", f"Correction from {mail['from']} before our quote", mail_data(later[-1]))
    read = read_request(merged)
    if read["missing"]:
        api.event(session_id, "routed", f"Correction not usable ({', '.join(read['missing'])}): first reading kept")
        return rfq, result, read["cost"]
    new = {**read["rfq"], **{k: rfq[k] for k in ("contact_name", "dg_declared") if rfq.get(k)}}
    new["dangerous_goods"] = bool(new.get("dangerous_goods") or rfq.get("dangerous_goods"))
    api.update(session_id, rfq=new)
    api.event(session_id, "extracted", f"Re-read with the correction: {new['origin']} → {new['destination']}",
              new, read["cost"])
    result = api.price(new, bids)
    api.event(session_id, "priced", f"{len(result['options'])} options. {result.get('why', '')}".strip(), result)
    return new, result, read["cost"]


FALLBACK_LATEST_SECONDS = 330  # the RFQ expires at 6:00; a later quote can't score


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
    # Pricing takes seconds: a person may have replied (with a price: quote set, paused off) in the meantime.
    session = api.session(session_id)
    if session.get("paused") or session.get("quote") or not session.get("needs_human"):
        return
    if time.time() - sent_at(mail) > FALLBACK_LATEST_SECONDS:
        return api.event(session_id, "needs_human", "Fallback: too late, the RFQ expires before a quote reaches 5U")
    text = quote_text(rfq, chosen, mail.get("body"))
    box.reply(mail, text)
    api.update(session_id, stage="quoted", needs_human=False, quote={**chosen, "sent_at": now(), "fallback": True})
    api.event(session_id, "quote_sent",
              f"Fallback quote sent: {chosen['currency']} {chosen['total']:,.2f} all-in ({result.get('why', '')[:120]})",
              {**reply_data(mail, text), "option": chosen})


def _price_and_quote(session_id, mail, rfq, cost, box, api, board, carriers, cutoff_s, attachments=(), doubt=False) -> None:
    """Carrier round, price, amendments, quote gate, quote in the customer's thread (shared by new RFQs and RFQs
    resumed after a question)."""
    bids, quoting = [], False
    try:
        excluded = {x.lower() for x in rfq.get("excluded_airlines") or []}
        targets = [c for c in carriers_for(carriers, rfq) if c["name"].lower() not in excluded]
        bids, bid_cost = _carrier_round(session_id, mail, rfq, targets, box, api, board, cutoff_s)
        if bids or bid_cost:
            api.update(session_id, bids=bids, llm_cost_usd=cost + bid_cost)

        result = api.price(rfq, bids)
        chosen = result["chosen"]
        api.event(session_id, "priced", f"{len(result['options'])} options. {result.get('why', '')}".strip(), result)
        if not chosen and (other := aliased(rfq)):  # HND has no lane today: price Tokyo at NRT, our lanes' airport
            alias_rfq, note = other
            alias_result = api.price(alias_rfq, bids)
            api.event(session_id, "priced", f"No price at {rfq['origin']}-{rfq['destination']}: {note}, "
                      f"{len(alias_result['options'])} options", alias_result)
            if alias_result.get("chosen"):
                rfq, result, chosen = alias_rfq, alias_result, alias_result["chosen"]
                api.update(session_id, rfq=rfq)
        if not chosen:
            hand_over(api, session_id, "No price found for this request")
            quoting = True
            return _fallback_quote(session_id, mail, rfq, bids, box, api)
        if later := amendments.take(mail["thread_id"]):  # the customer corrected the request while we priced it
            rfq, result, extra = _reread(session_id, mail, later, rfq, bids, api, result)
            chosen, cost = result["chosen"], cost + extra
            api.update(session_id, llm_cost_usd=cost + bid_cost)
            if not chosen:
                hand_over(api, session_id, "No price found after the customer's correction")
                quoting = True
                return _fallback_quote(session_id, mail, rfq, bids, box, api)

        text, chosen, hold = _gate(session_id, mail, rfq, result, attachments, api)
        if hold and not _hold(session_id, mail, api):
            return  # a person took over in the Sessions UI
        if doubt and (wait := sent_at(mail) + FALLBACK_AT_SECONDS - time.time()) > 0:
            _sleep(wait)  # the person's window for numbers that looked odd (a gate hold above may already be longer)
        current = api.session(session_id)
        if current.get("paused") or current.get("quote"):
            return  # a person took over in the Sessions UI, or already quoted by hand: never a second quote
        quoting = True  # from here on a crash must never send again
        box.reply(mail, text)
        api.update(session_id, stage="quoted", quote={**chosen, "sent_at": now()}, **({"needs_human": False} if doubt else {}))
        api.event(session_id, "quote_sent",
                  f"Quote sent: {chosen['currency']} {chosen['total']:,.2f} all-in ({rfq['ask']})",
                  {**reply_data(mail, text), "option": chosen})
    except Exception as error:
        if quoting or not CRASH_FALLBACK:
            raise  # a send started (or the fallback is off): never a second quote
        api.update(session_id, stage="failed", needs_human=True)  # a crash scores 0: the fallback quote still tries
        api.event(session_id, "error", f"{type(error).__name__}: {error}")
        try:
            _fallback_quote(session_id, mail, rfq, bids, box, api)
        except Exception as again:
            api.event(session_id, "error", f"Fallback after the error failed too: {type(again).__name__}: {again}")

def _ask_for_pickup(session_id: int, mail: dict, rfq: dict, box, api) -> None:
    """Ask the customer where we pick up (no price yet: the quote follows their answer in the same thread)."""
    if api.session(session_id).get("paused"):
        return
    rfq["awaiting"] = "pickup"
    api.update(session_id, rfq=rfq)  # before the mail: a fast answer must find the session waiting for it
    box.reply(mail, pickup_question_text(rfq))
    api.event(session_id, "routed", "No pickup address: asked the customer for the pickup postcode")


_answered: set = set()  # sessions whose pickup answer is being handled
_answer_lock = threading.Lock()


def resume_after_pickup(mail: dict, box, api, board, carriers, session: dict) -> None:
    """The customer answered where to pick up ("pickup location: 84236 Landshut"): price and quote now."""
    session_id, rfq = session["id"], dict(session.get("rfq") or {})
    with _answer_lock:  # two quick mails while waiting must not start two quotes
        if session_id in _answered:
            return amendments.add(mail["thread_id"], mail)
        _answered.add(session_id)
    api.event(session_id, "mail_in", f"Reply from {mail['from']}: {mail['subject']}", mail_data(mail))
    try:
        try:  # the RFQ itself: its time drives the cut-offs, its text and attachments the gate
            rfq_mail = box.get(session["thread_id"])
        except Exception:
            rfq_mail = {**mail, "received_at": session.get("received_at")}
        if time.time() - sent_at(rfq_mail) > FALLBACK_LATEST_SECONDS:
            return hand_over(api, session_id, "Customer answered too late: the RFQ expires before a quote reaches 5U")
        text = latest_text(mail["body"])
        postcode = re.search(r"\b(\d{5})\b", text)
        line = next((l.strip() for l in text.splitlines() if postcode and postcode.group(1) in l), text.strip()[:120])
        zone = postcode.group(1)[:2] if postcode else city_zone(text)
        pickup = {"address": line, "zone": zone}
        origin = zone_airport(pickup) if zone else None
        if not origin:
            return hand_over(api, session_id, "Customer answered, but no pickup postcode or known town in it")
        rfq.pop("awaiting", None)
        rfq["pickup"], rfq["origin"] = pickup, origin
        api.update(session_id, rfq=rfq)
        api.event(session_id, "extracted", f"Pickup {line} → {origin}", rfq)
        _price_and_quote(session_id, rfq_mail, rfq, session.get("llm_cost_usd") or 0.0, box, api, board, carriers,
                         BID_CUTOFF_SECONDS, _attachment_texts(session_id, rfq_mail, box, api))
    except Exception as error:
        api.update(session_id, stage="failed", needs_human=True)
        api.event(session_id, "error", f"{type(error).__name__}: {error}")
