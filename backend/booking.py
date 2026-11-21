"""POST /api/book: book the quoted option on the 5U portal by rate ID, with a fresh rate if the quoted one expired.

Portal answers: 201 booked · 200 the same retry · 404 unknown rate_id · 409 booked under another reference ·
410 expired (fetch a fresh rate and book that) · 503 booking down, book by email with the airline.
"""

import os

from pricing import Pricer, weights

MAX_FRESH_INCREASE = 0.05  # a fresh rate after expiry may cost at most 5 % more than the quote, else a person decides
# OFF by default (Sat 19:45): the board disproves the theory below. Rounds 26, 28 and 30 were booked with the
# airline's email-bid rate ID too and DID count (booked: true); booking a fresh portal rate instead books a different
# offer than the one quoted, against the likeliest rule (5U counts a booking of the exact quoted offer). BOOK_BIDS_VIA_PORTAL=on
# turns it back on.
# R27, R29: a door-to-port quote booked with the airline's email-bid rate ID got booked=false at 5U (no tracking +10);
# portal-rate bookings count. So a bid winner is booked as a fresh portal rate of the same airline when the portal
# has one at no more than the quoted air price + 5 %; the bid's own rate ID stays the fallback. Off: BOOK_BIDS_VIA_PORTAL=off
BOOK_BIDS_VIA_PORTAL = os.environ.get("BOOK_BIDS_VIA_PORTAL", "off").lower() == "on"


class BookingError(Exception):
    """The portal can't book this; `detail` says why (the agent flags the session for a person)."""


async def book(pricer: Pricer, session: dict, rate_id: str | None, remember=lambda rate_id: None) -> tuple[dict, str | None]:
    """(BookingOut, note). The note says what happened besides a plain booking (re-priced rate), else None.

    remember(rate_id) stores a fresh rate on the session before it is booked, so a lost portal answer can't lead to a
    second booking: the next call retries that same rate first.
    """
    quote = session.get("quote") or {}
    pending = (session.get("booking") or {}).get("pending_rate_id")
    rate_id = pending or rate_id or quote.get("rate_id")
    reference = f"S-{session['id']}"
    if (BOOK_BIDS_VIA_PORTAL and not pending and quote.get("source") == "carrier_bid"
            and str(rate_id or "").startswith("R-")):
        fresh = await _fresh_rate(pricer, session)
        try:
            if fresh:
                _check_price(fresh, quote, rate_id)
        except BookingError:
            fresh = None  # the portal is dearer than the bid: book the bid's own rate
        if fresh:
            remember(fresh["rate_id"])
            response = await pricer.portal.book(fresh["rate_id"], reference)
            if response.status_code in (200, 201):
                pricer.portal.forget(fresh["rate_id"])
                return response.json(), (f"carrier_bid option {quote.get('carrier')} booked as portal rate "
                                         f"{fresh['rate_id']} ({fresh['currency']} {fresh['total']}; bid rate {rate_id})")
            if _portal_down(response):
                _raise_for(response)
            if response.status_code not in (404, 409, 410):  # unclear (5xx, …): it may be booked, so never book a 2nd
                raise BookingError(f"portal booking {response.status_code} for {fresh['rate_id']}: unclear whether it "
                                   "went through; the next try books that same rate (pending), never the bid's too")
        # no portal rate (rate API down) or the portal clearly refused it (404/409/410): the bid's rate ID below
    if not rate_id or not str(rate_id).startswith("R-"):
        # A sheet or carrier-bid winner: if its airline is on the portal for this lane, book a fresh portal rate
        # (every booking earns the +10 tracking bonus later); otherwise it has to be booked by email.
        fresh = await _fresh_rate(pricer, session)
        if fresh is None:
            raise BookingError(f"{quote.get('carrier', 'this option')} has no portal rate ID ({quote.get('source')} "
                               "option) and is not on the portal for this lane: book it by email with the airline")
        _check_price(fresh, quote, rate_id)
        remember(fresh["rate_id"])
        response = await pricer.portal.book(fresh["rate_id"], reference)
        if response.status_code in (200, 201):
            pricer.portal.forget(fresh["rate_id"])
            return response.json(), (f"{quote.get('source')} option {quote.get('carrier')} booked through the portal: "
                                     f"rate {fresh['rate_id']} ({fresh['currency']} {fresh['total']})")
        _raise_for(response)

    response = await pricer.portal.book(rate_id, reference)
    if (first := response.status_code) in (410, 409):  # expired, or taken by another of our sessions (cached rate)
        fresh = await _fresh_rate(pricer, session)
        if fresh is None:
            raise BookingError(f"rate {rate_id} can't be booked ({response.status_code}) and no fresh portal rate "
                               f"for {quote.get('carrier')}")
        _check_price(fresh, quote, rate_id)
        remember(fresh["rate_id"])
        response = await pricer.portal.book(fresh["rate_id"], reference)
        if response.status_code in (200, 201):
            pricer.portal.forget(fresh["rate_id"])
            note = (f"Rate {rate_id} {'expired' if first == 410 else 'already booked'}: booked a fresh rate {fresh['rate_id']} "
                    f"({fresh['currency']} {fresh['total']}, quoted {quote.get('currency') or 'EUR'} {quote.get('total')})")
            return response.json(), note
    if response.status_code in (200, 201):
        pricer.portal.forget(rate_id)
        return response.json(), None
    _raise_for(response)


async def _fresh_rate(pricer: Pricer, session: dict) -> dict | None:
    """The quoted airline's current rate on the same lane, at the weight the quote was billed at."""
    rfq, quote = session.get("rfq") or {}, session.get("quote") or {}
    code = quote.get("airline_code") or quote.get("carrier")
    origin, destination, _ = pricer.lane(rfq, [])
    if not (code and origin and destination):
        return None
    actual, cbm = weights(rfq)
    billed, chargeable = quote.get("billed_weight_kg"), quote.get("chargeable_weight_kg")
    if billed and chargeable and billed > chargeable:  # quoted at a higher break: ask for that break again
        return await pricer.portal.rate(origin, destination, code, billed, 0, fresh=True)
    return await pricer.portal.rate(origin, destination, code, actual, cbm, fresh=True)


def _check_price(fresh: dict, quote: dict, rate_id) -> None:
    """A fresh rate may cost at most MAX_FRESH_INCREASE more than the air part of the quote."""
    fresh_eur = float(fresh["total"]) * (float(fresh.get("fx_eur_per_usd") or 1) if fresh.get("currency") != "EUR" else 1)
    quoted = quote.get("total_eur") if quote.get("currency") not in (None, "EUR") else quote.get("total")  # a USD quote
    quoted_air = float(quoted or quote.get("total") or 0) - float((quote.get("pickup") or {}).get("total") or 0)
    if quoted_air and fresh_eur > quoted_air * (1 + MAX_FRESH_INCREASE):
        raise BookingError(f"rate {rate_id}: the fresh air rate costs EUR {fresh_eur:,.2f}, quoted air "
                           f"EUR {quoted_air:,.2f}: a person decides")


def _portal_down(response) -> bool:
    """R45: 503 "The rate portal is down. Contact the airline directly.": surely not booked, the airline books by mail."""
    text = (response.text or "").lower()  # R52: "Booking is not available for Nova Atlas Cargo. Please book by email"
    return response.status_code == 503 and any(p in text for p in ("contact the airline", "book by email", "by e-mail",
                                                                   "booking is not available", "email the airline"))


def _raise_for(response) -> None:
    if _portal_down(response):  # the agent's email booking path reacts to this exact phrase (booking_agent.EMAIL_ONLY)
        raise BookingError(f"portal booking 503, the portal is down ({response.text[:160]}): "
                           "book it by email with the airline")
    raise BookingError(f"portal booking {response.status_code}: {response.text[:300]}")
