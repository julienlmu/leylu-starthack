"""RFQ agent (MVP): extract → price → quote in the customer's thread.

shortcut: quotes straight from sheet and portal prices; the carrier round with a cut-off comes in A4.
"""

from backend import now
from extract import extract, to_rfq
from templates import quote_text


def handle_rfq(mail: dict, box, api) -> None:
    session_id = api.create_session(mail["from"], mail["thread_id"])
    api.event(session_id, "mail_in", f"RFQ from {mail['from']}: {mail['subject']}")
    api.event(session_id, "routed", "New RFQ (rules, no LLM)")
    try:
        raw, cost = extract(mail)
        rfq, missing = to_rfq(raw)
        api.update(session_id, stage="pricing", rfq=rfq, llm_cost_usd=cost)
        api.event(session_id, "extracted", f"{rfq['origin']} → {rfq['destination']}, {rfq['ask']}", rfq, cost)
        if missing:
            return _hand_over(api, session_id, f"Can't price yet, missing: {', '.join(missing)}")

        result = api.price(rfq)
        chosen = result["chosen"]
        api.event(session_id, "priced", f"{len(result['options'])} options. {result.get('why', '')}".strip(), result)
        if not chosen:
            return _hand_over(api, session_id, "No price found for this request")

        if api.session(session_id).get("paused"):
            return  # a person took over in the Sessions UI
        box.reply(mail, quote_text(rfq, chosen))
        api.update(session_id, stage="quoted", quote={**chosen, "sent_at": now()})
        api.event(session_id, "quote_sent",
                  f"Quote sent: {chosen['currency']} {chosen['total']:,.2f} all-in ({rfq['ask']})", chosen)
    except Exception as error:  # one broken mail must not stop the worker; the session shows what happened
        api.update(session_id, stage="failed", needs_human=True)
        api.event(session_id, "error", f"{type(error).__name__}: {error}")


def _hand_over(api, session_id: int, reason: str) -> None:
    api.update(session_id, needs_human=True)
    api.event(session_id, "needs_human", reason)
