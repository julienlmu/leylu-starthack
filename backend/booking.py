"""POST /api/book: book the quoted option on the 5U portal by rate ID, with a fresh rate if the quoted one expired.

Portal answers: 201 booked · 200 the same retry · 404 unknown rate_id · 409 booked under another reference ·
410 expired (fetch a fresh rate and book that) · 503 booking down, book by email with the airline.
"""

from pricing import Pricer, weights


class BookingError(Exception):
    """The portal can't book this; `detail` says why (the agent flags the session for a person)."""


async def book(pricer: Pricer, session: dict, rate_id: str | None) -> tuple[dict, str | None]:
    """(BookingOut, note). The note says what happened besides a plain booking (re-priced rate), else None."""
    quote = session.get("quote") or {}
    rate_id = rate_id or quote.get("rate_id")
    reference = f"S-{session['id']}"
    if not rate_id or not str(rate_id).startswith("R-"):
        raise BookingError(f"{quote.get('carrier', 'this option')} has no portal rate ID ({quote.get('source')} "
                           "option): book it by email with the airline")

    response = await pricer.portal.book(rate_id, reference)
    if response.status_code == 410:
        fresh = await _fresh_rate(pricer, session)
        if fresh is None:
            raise BookingError(f"rate {rate_id} expired and no fresh portal rate for {quote.get('carrier')}")
        response = await pricer.portal.book(fresh["rate_id"], reference)
        if response.status_code in (200, 201):
            note = (f"Rate {rate_id} expired: booked a fresh rate {fresh['rate_id']} "
                    f"({fresh['currency']} {fresh['total']}, quoted EUR {quote.get('total')})")
            return response.json(), note
    if response.status_code in (200, 201):
        return response.json(), None
    raise BookingError(f"portal booking {response.status_code}: {response.text[:300]}")


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
