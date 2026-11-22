"""A person feeds a rate from the portal's web form (start-hack.5u.ai/portal/ui) into a session whose portal API is down.

    cd agent && uv run --env-file ../.env python portal_rate.py <session>                      # what to type in the form
    cd agent && uv run --env-file ../.env python portal_rate.py <session> <airline> <EUR total> [days] [rate ID]

The rate is stored as a bid with `manual_portal: true`; the RFQ agent (rfq_agent._portal_retry) picks it up within
seconds, prices again with it and quotes. Talks only to the local backend (BACKEND_URL); no mail, no 5U call, no LLM.
"""

import sys

from backend import Backend


def stored_rate(airline: str, total: str, days: str | None = None, rate_id: str | None = None) -> dict:
    return {"source": "carrier_bid", "leg": "air", "carrier": airline, "currency": "EUR",
            "total": float(total.replace(",", "")), "transit_days": float(days) if days else None,
            "rate_id": rate_id, "manual_portal": True}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    import rfq_agent
    api, session_id = Backend(), int(argv[0])
    session = api.session(session_id)
    rfq = session.get("rfq") or {}
    if len(argv) < 3:
        print(f"Session {session_id}: {rfq_agent.portal_form(rfq)}")
        return 0
    rate = stored_rate(*argv[1:5])
    api.update(session_id, bids=[*(session.get("bids") or []), rate])
    print(f"Session {session_id}: {rate['carrier']} EUR {rate['total']:,.2f} stored; the agent quotes with it shortly")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
