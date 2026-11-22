"""Pricing: every all-in way to fly an Rfq (rate sheets, portal, carrier bids) and the one to quote. No LLM.

Rules from the start kit (identical in all 10 sheets):
- chargeable kg = max(actual kg, cbm × 167)
- freight = max(minimum, rate × billed kg); the minimum applies to the freight before surcharges
- fuel and security are per kg of the billed weight
- billing at a higher weight break is allowed and often cheaper: price the own bracket and every higher break
Money is rounded half-up to cents per line; the total is the sum of the lines.
"""

import asyncio
import csv
import os
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from portal import Portal
from tariffs import Tariffs, Zones

CBM_KG = 167
MAX_HIGHER_BREAKS = 2  # portal: next breaks up to ask for (each one is a rate-limited call)
# A higher break can only be cheaper when it is close: across all 10 sheets the all-in rate per kg drops at most
# ×1.32 from one break to the next, so a break more than 1.5× the chargeable weight is never cheaper.
NEXT_BREAK_RATIO = 1.5
# Which option to pick among carrier bids. ❓ 5U: "price and speed weigh 50/50" (PLAN.md §10.1).
# Pickup leg: the trucker picked ratio-balanced 50/50 on price and days (price/cheapest + days/fastest). It matches 5U's
# best price in every door-to-port round so far: round 2 (Bodenseefracht, cheapest and balanced), round 4 (Westfalenroute,
# full 60), round 9 (cheapest Vogelsberg was 3.2 % below 5U's best: 45.59 instead of 60).
PICKUP_CHOICE = os.environ.get("PICKUP_CHOICE", "balanced")            # trucker bids for door-to-port
BIDS_ONLY_CHOICE = os.environ.get("BIDS_ONLY_CHOICE", "ask")           # lanes priced by airline bids only
PORTAL_DEADLINE_S = float(os.environ.get("PORTAL_DEADLINE_S", "5"))  # /api/price waits this long for the portal
BALANCED_FORMULA = os.environ.get("BALANCED_FORMULA", "ratio")         # ratio | minmax


def _fallback_fx(raw: str) -> dict[str, float]:
    """FX_FALLBACK="USD:0.86,CHF:1.07,GBP:1.15" (EUR per 1 unit): used only for a currency the portal never stated, so a
    CHF bid is compared instead of dropped. "off" = bids in such a currency are skipped, as before."""
    if raw.strip().lower() == "off":
        return {}
    out = {}
    for part in raw.split(","):
        code, _, rate = part.partition(":")
        try:
            if code.strip() and float(rate) > 0:
                out[code.strip().upper()] = float(rate)
        except ValueError:
            continue
    return out


def _fx_table(path) -> dict[str, float]:
    """data/fx_eur.csv: a fixed EUR-per-unit table kept in the repo (no live FX call). Used only for a currency the portal
    never stated; FX_FALLBACK="CHF:1.05" overrides single rates, FX_FALLBACK=off drops the table too."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return {r["code"].strip().upper(): float(r["eur_per_unit"]) for r in csv.DictReader(f)
                    if r.get("code") and float(r.get("eur_per_unit") or 0) > 0}
    except (OSError, ValueError, KeyError):
        return {"USD": 0.86, "CHF": 1.07, "GBP": 1.15}


FX_TABLE = _fx_table(Path(__file__).resolve().parent / "data" / "fx_eur.csv")
_FX_ENV = os.environ.get("FX_FALLBACK", "")
FX_FALLBACK = {} if _FX_ENV.strip().lower() == "off" else {**FX_TABLE, **_fallback_fx(_FX_ENV)}


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def kg(x) -> str:
    return f"{float(x):,.10g}"


def weights(rfq: dict) -> tuple[float, float]:
    """(actual kg, volume cbm) of the whole shipment. weight_kg and dims are per piece."""
    pieces = rfq.get("pieces") or []
    actual = sum((p.get("count") or 1) * (p.get("weight_kg") or 0) for p in pieces)
    if pieces and all(p.get("length_cm") and p.get("width_cm") and p.get("height_cm") for p in pieces):
        cbm = sum((p.get("count") or 1) * p["length_cm"] * p["width_cm"] * p["height_cm"] for p in pieces) / 1e6
    else:
        cbm = rfq.get("volume_m3") or 0
    return round(actual, 2), round(cbm, 6)  # per-piece weights may carry 1e-6 kg of rounding: book the full kg


def chargeable_kg(actual: float, cbm: float, cbm_kg: float = CBM_KG) -> float:
    return round(max(actual, cbm * cbm_kg), 3)


def sheet_option(sheet: dict, lane: dict, actual: float, cbm: float) -> dict:
    """The cheapest way to bill this lane: own bracket or a higher break."""
    chargeable = chargeable_kg(actual, cbm, sheet.get("cbm_kg") or CBM_KG)
    breaks = sheet["breaks_kg"]
    own = max(i for i, b in enumerate(breaks) if b <= chargeable)
    best = None
    for i in range(own, len(breaks)):
        billed = Decimal(str(chargeable if i == own else breaks[i]))
        rate = Decimal(str(lane["rates"][i]))
        minimum = Decimal(str(lane["minimum"]))
        freight = money(max(minimum, rate * billed))
        fuel = money(Decimal(str(lane["fuel"])) * billed)
        security = money(Decimal(str(lane["security"])) * billed)
        total = freight + fuel + security
        if best is None or total < best[0]:
            freight_label = (f"Freight minimum ({kg(billed)} kg × {rate} below {minimum})" if minimum > rate * billed
                             else f"Freight {kg(billed)} kg × {rate}")
            best = (total, billed, [
                {"label": freight_label, "amount": float(freight)},
                {"label": f"Fuel {kg(billed)} kg × {lane['fuel']:.2f}", "amount": float(fuel)},
                {"label": f"Security {kg(billed)} kg × {lane['security']:.2f}", "amount": float(security)}])
    total, billed, breakdown = best
    return {"source": "sheet", "leg": "air", "carrier": sheet["airline"], "rate_id": None,
            "currency": sheet.get("currency", "EUR"), "total": float(total), "total_eur": float(total),
            "transit_days": lane["transit_days"], "valid_until": sheet["valid_to"],
            "chargeable_weight_kg": chargeable, "billed_weight_kg": float(billed), "breakdown": breakdown}


def portal_option(rate: dict, actual: float) -> dict | None:
    """A portal rate as an all-in EUR option (non-EUR totals converted with the fx the portal states)."""
    try:
        total = Decimal(str(rate["total"]))
        currency = rate.get("currency") or "EUR"
        if currency == "EUR":
            eur, label = money(total), f"Air freight {rate['airline']} (freight + fuel + security)"
        else:
            fx = Decimal(str(rate["fx_eur_per_usd"]))
            eur = money(total * fx)
            label = f"Air freight {rate['airline']}: {currency} {total} × {fx} EUR/{currency}"
        billed = float(rate.get("chargeable_weight_kg") or actual)
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
    return {"source": "portal", "leg": "air", "carrier": rate["airline"], "airline_code": rate.get("airline_code"),
            "rate_id": rate["rate_id"], "currency": "EUR", "total": float(eur), "total_eur": float(eur),
            "transit_days": rate.get("transit_days"), "valid_until": rate.get("valid_until"),
            "chargeable_weight_kg": billed, "billed_weight_kg": billed,
            "breakdown": [{"label": f"{label}, {kg(billed)} kg", "amount": float(eur)}]}


def bid_option(bid: dict, fx: dict[str, float]) -> dict | None:
    """A carrier bid from the agent, in EUR. None if its currency can't be converted."""
    currency = (bid.get("currency") or "EUR").upper()
    try:
        total = Decimal(str(bid["total"]))
    except (KeyError, TypeError, ArithmeticError):
        return None
    stated = ""
    if currency != "EUR":
        if currency not in fx:
            return None
        stated = f": {currency} {float(total):,.2f} × {fx[currency]:g} EUR/{currency}"
        total = total * Decimal(str(fx[currency]))
    eur = float(money(total))
    leg = bid.get("leg") or "air"
    label = f"{'Pickup' if leg == 'pickup' else 'Air freight'} {bid.get('carrier', '')} (bid){stated}"
    return {"source": "carrier_bid", "leg": leg, "carrier": bid.get("carrier", ""), "rate_id": bid.get("rate_id"),
            "currency": "EUR", "total": eur, "total_eur": eur, "transit_days": bid.get("transit_days"),
            "valid_until": bid.get("valid_until"), "chargeable_weight_kg": bid.get("chargeable_weight_kg"),
            "breakdown": bid.get("breakdown") or [{"label": label, "amount": eur}]}


def with_pickup(option: dict, truck: dict, zone: dict | None) -> dict:
    """Door-to-port: the air option plus the trucker's pickup, as one all-in total."""
    where = f"zone {zone['zone']} ({zone['area']})" if zone else "your address"
    total = float(money(Decimal(str(option["total"])) + Decimal(str(truck["total"]))))
    transit = None if option["transit_days"] is None else option["transit_days"] + (truck["transit_days"] or 0)
    return {**option, "total": total, "total_eur": total, "transit_days": transit,
            "breakdown": [*option["breakdown"], {"label": f"Pickup {where} by {truck['carrier']}", "amount": truck["total"]}],
            "pickup": {"carrier": truck["carrier"], "rate_id": truck["rate_id"], "total": truck["total"],
                       "transit_days": truck["transit_days"]}}


def choose(options: list[dict], mode: str) -> dict | None:
    """cheapest: lowest total (then faster) · fastest: fewest days (then cheaper) · balanced: price and days 50/50."""
    if not options:
        return None
    known = [o["transit_days"] for o in options if o["transit_days"] is not None]
    slowest = (max(known) + 1) if known else 1
    days = {id(o): o["transit_days"] if o["transit_days"] is not None else slowest for o in options}
    if mode == "fastest":
        return min(options, key=lambda o: (days[id(o)], o["total"]))
    if mode == "balanced":
        prices, spans = [o["total"] for o in options], list(days.values())
        if BALANCED_FORMULA == "minmax":
            def part(v, vs):
                return (v - min(vs)) / (max(vs) - min(vs)) if max(vs) > min(vs) else 0.0
        else:
            def part(v, vs):
                return v / min(vs) if min(vs) > 0 else v + 1
        return min(options, key=lambda o: (0.5 * part(o["total"], prices) + 0.5 * part(days[id(o)], spans), o["total"]))
    return min(options, key=lambda o: (o["total"], days[id(o)]))


class Pricer:
    def __init__(self, tariffs: Tariffs, zones: Zones, portal: Portal):
        self.tariffs, self.zones, self.portal = tariffs, zones, portal
        self._background: set[asyncio.Task] = set()
        self._pricing: dict[tuple, int] = {}  # lookups in flight per (lane, weight): prefetch + /api/price share one

    def lane(self, rfq: dict, notes: list[str]) -> tuple[str, str, dict | None]:
        """(origin, destination, pickup zone). Door-to-port flies from the pickup zone's airport."""
        origin = (rfq.get("origin") or "").upper()
        destination = (rfq.get("destination") or "").upper()
        zone = self.zones.resolve(rfq.get("pickup"))
        if rfq.get("pickup"):
            if zone is None:
                notes.append("pickup zone unknown (no German postcode)")
            elif zone["airport"] != origin:
                notes.append(f"pickup zone {zone['zone']} ({zone['area']}) flies from {zone['airport']}")
                origin = zone["airport"]
        return origin, destination, zone

    async def prefetch(self, rfq: dict) -> None:
        """Asks the portal as soon as the RFQ is extracted, so /api/price at the bid cut-off is answered from cache."""
        origin, destination, _ = self.lane(rfq, [])
        actual, cbm = weights(rfq)
        if origin and destination and actual > 0:
            await self._portal_options(origin, destination, actual, cbm)

    async def price(self, rfq: dict, bids: list[dict] | None = None) -> dict:
        notes: list[str] = []
        origin, destination, zone = self.lane(rfq, notes)
        actual, cbm = weights(rfq)
        if not origin or not destination or actual <= 0:
            return {"options": [], "chosen": None, "why": "Can't price: origin, destination or weight missing"}
        on = _date(rfq.get("ready_date"))

        air = []
        for sheet, lane in self.tariffs.lanes(origin, destination, on):
            option = in_eur(sheet_option(sheet, lane, actual, cbm), self.portal.fx)
            if option is None:
                notes.append(f"{sheet['airline']} sheet in {sheet.get('currency')} skipped (no exchange rate yet)")
            else:
                air.append(option)
        portal = await self._portal_options(origin, destination, actual, cbm, PORTAL_DEADLINE_S, notes)
        if not portal and self.portal.last_error and await self.portal.airlines(origin, destination):
            notes.append(f"portal: {self.portal.last_error[:600]}")  # R93-R95: the 503 detail was cut at "The rat"
        air += portal
        fx = self.fx()
        converted = [(b, bid_option(b, fx)) for b in bids or []]
        if skipped := [b.get("carrier", "?") for b, o in converted if o is None]:
            notes.append(f"bids in an unknown currency skipped: {', '.join(skipped)}")
        for b, o in converted:
            if o and (cur := (b.get("currency") or "EUR").upper()) not in ("EUR", *self.portal.fx):
                notes.append(f"{b.get('carrier', '?')} bid in {cur} converted at the fallback rate {fx[cur]:g} EUR/{cur} "
                             "(the portal never stated one)")
        air += [o for _, o in converted if o and o["leg"] != "pickup"]
        trucks = [o for _, o in converted if o and o["leg"] == "pickup"]
        air, odd_air = _sane_air(air, actual, cbm)
        if odd_air:
            notes.append(f"airline bids dropped as implausible: {', '.join(odd_air)}")
        trucks, odd = _sane_trucks(trucks, actual, cbm)
        if odd:
            notes.append(f"trucker bids dropped as implausible: {', '.join(odd)}")
        if excluded := {str(x).lower() for x in rfq.get("excluded_airlines") or [] if x}:
            # "Please do not offer Zephyr Steppe Cargo (ZS)" (round 42, rejected excluded_airline): never quote them
            kept = [o for o in air if (o.get("carrier") or "").lower() not in excluded
                    and (o.get("airline_code") or "").lower() not in excluded]
            if len(kept) < len(air):
                notes.append(f"excluded by the customer: {', '.join(sorted(excluded))}")
            air = kept
            # "Please don't use Spessart Spedition for the pickup": the same rule for the trucker leg
            trucks = [t for t in trucks if (t.get("carrier") or "").lower() not in excluded]
        counts = {s: sum(o["source"] == s for o in air) for s in ("sheet", "portal", "carrier_bid")}
        summary = f"{len(air)} air options (sheet {counts['sheet']}, portal {counts['portal']}, bids {counts['carrier_bid']})"

        if rfq.get("pickup"):
            if not trucks:
                notes.append("door-to-port but no trucker bid: no all-in price")
                return {"options": sorted(air, key=lambda o: o["total"]), "chosen": None,
                        "why": "; ".join([summary, *notes])}
            pick = _mode(rfq) if PICKUP_CHOICE == "ask" else PICKUP_CHOICE
            truck = choose(trucks, pick)
            notes.append(f"pickup by {truck['carrier']} EUR {truck['total']:,.2f} ({pick} of {len(trucks)})")
            air = [with_pickup(o, truck, zone) for o in air]

        mode = _mode(rfq)
        if air and all(o["source"] == "carrier_bid" for o in air) and BIDS_ONLY_CHOICE != "ask":
            mode = BIDS_ONLY_CHOICE
        chosen = choose(air, mode)
        if chosen is None:
            return {"options": [], "chosen": None, "why": "; ".join([f"No price for {origin}-{destination}", *notes])}
        days = f"{chosen['transit_days']:g} d, " if chosen["transit_days"] is not None else ""
        why = f"{mode}: {chosen['carrier']} ({chosen['source']}) {days}EUR {chosen['total']:,.2f}; {summary}"
        warnings = await self._guard(rfq, chosen, air, origin, destination, actual, cbm, on)
        return {"options": sorted(air, key=lambda o: o["total"]), "chosen": chosen, "warnings": warnings,
                "why": "; ".join([why, *notes, *(f"CHECK: {w}" for w in warnings)]), "fx": fx}

    def fx(self) -> dict[str, float]:
        """EUR per 1 unit: what the portal last stated, else FX_FALLBACK."""
        return {**FX_FALLBACK, **self.portal.fx}

    async def _guard(self, rfq: dict, chosen: dict, air: list[dict], origin: str, destination: str,
                     actual: float, cbm: float, on: str) -> list[str]:
        """Checks before the quote goes out (SCORE_ANALYSIS R1). They only warn: an answer always beats none."""
        warnings = []
        if rfq.get("pickup") and not chosen.get("pickup"):
            warnings.append("door-to-port quote without a pickup leg (5U rejects it as too_low)")
        volumetric = round(cbm * CBM_KG, 2)
        charged = chosen.get("chargeable_weight_kg")
        if charged is not None and charged + 0.01 < max(actual, volumetric):
            warnings.append(f"charged {charged:g} kg < max(actual {actual:g}, volume {volumetric:g}) kg")
        sheets = len(self.tariffs.lanes(origin, destination, on))
        try:  # the lane list is cached by now; never wait for a slow portal here (the quote's time counts)
            portal = len(await asyncio.wait_for(self.portal.airlines(origin, destination), 0.2))
        except asyncio.TimeoutError:
            portal = 0
        priced = sum(o["source"] in ("sheet", "portal") for o in air)
        if priced < sheets + portal:
            warnings.append(f"only {priced} of {sheets + portal} sheet/portal sources priced")
        per_kg = [float(o["total"]) / max(float(o.get("billed_weight_kg") or o.get("chargeable_weight_kg") or 1), 1)
                  for o in air if o["source"] == "sheet"]
        mine = float(chosen["total"]) / max(float(chosen.get("billed_weight_kg") or chosen.get("chargeable_weight_kg") or actual or 1), 1)
        if per_kg and not (0.5 * min(per_kg) <= mine <= 2 * max(per_kg)):
            warnings.append(f"EUR {mine:.2f}/kg is far from the sheets' EUR {min(per_kg):.2f}–{max(per_kg):.2f}/kg")
        return warnings

    async def _portal_options(self, origin: str, destination: str, actual: float, cbm: float,
                              deadline: float | None = None, notes: list[str] | None = None) -> list[dict]:
        """Portal options found within `deadline` seconds. Slower lookups keep running and fill the cache."""
        start = asyncio.get_running_loop().time()
        try:
            airlines = await asyncio.wait_for(self.portal.airlines(origin, destination), deadline)
        except asyncio.TimeoutError:
            if notes is not None:
                notes.append("portal lane list too slow, priced without the portal")
            return []
        if deadline is not None:
            deadline = max(0.1, deadline - (asyncio.get_running_loop().time() - start))
        turns = _Turns(len(airlines))
        turns.lookup = (origin, destination, actual, cbm)
        tasks = [asyncio.ensure_future(self._portal_best(origin, destination, a["code"], actual, cbm, turns))
                 for a in airlines]
        if not tasks:
            return []
        self._pricing[turns.lookup] = self._pricing.get(turns.lookup, 0) + 1
        try:
            done, pending = await asyncio.wait(tasks, timeout=deadline)
        finally:
            if (left := self._pricing.pop(turns.lookup) - 1) > 0:
                self._pricing[turns.lookup] = left
        for task in pending:
            self._background.add(task)
            task.add_done_callback(self._background.discard)
        if pending and notes is not None:
            notes.append(f"portal too slow for {len(pending)} airline(s), priced without them")
        return [t.result() for t in done if t.exception() is None and t.result()]

    async def _portal_best(self, origin: str, destination: str, code: str, actual: float, cbm: float,
                           turns: "_Turns | None" = None) -> dict | None:
        """Own bracket, then the next breaks up while they get cheaper (the portal doesn't check them for us)."""
        turns, best = turns or _Turns(1), None
        try:
            best = portal_option(rate, actual) if (rate := await self.portal.rate(origin, destination, code, actual, cbm)) else None
        finally:
            turns.own(code, best["total"] if best else None)
        if best is None:
            return None
        try:
            await turns.wait(code)
            # the reserve is only dipped into while no other RFQ is pricing: its must-have own brackets need it
            alone = all(lookup == turns.lookup for lookup in self._pricing)
            return await self._next_breaks(origin, destination, code, best, lead=alone and code == turns._first())
        finally:
            turns.done(code)

    async def _next_breaks(self, origin: str, destination: str, code: str, best: dict, lead: bool = False) -> dict:
        chargeable = best["chargeable_weight_kg"]
        higher = [b for b in await self.portal.brackets(code)
                  if chargeable < b < chargeable * NEXT_BREAK_RATIO][:MAX_HIGHER_BREAKS]
        for weight in higher:
            rate = await self.portal.rate(origin, destination, code, weight, 0, optional=True, lead=lead)
            option = portal_option(rate, weight) if rate else None
            if option is None or option["total"] >= best["total"]:
                break
            best = {**option, "chargeable_weight_kg": chargeable,
                    "breakdown": [{**option["breakdown"][0],
                                   "label": option["breakdown"][0]["label"] + f" (billed at the {kg(weight)} kg break)"}]}
        return best


class _Turns:
    """Next-break checks start with the airline whose own bracket is cheapest: the minute's few optional portal calls
    go where a cheaper break can change the quote, not to whichever airline answered first (trap 16)."""
    WAIT_S = 1.5  # never hold a check longer than this for a slow airline

    def __init__(self, airlines: int):
        self.airlines, self.totals, self.lookup = airlines, {}, None
        self.all_in, self.first_done = asyncio.Event(), asyncio.Event()

    def own(self, code: str, total: float | None) -> None:
        self.totals[code] = total
        if len(self.totals) >= self.airlines:
            self.all_in.set()

    def _first(self) -> str | None:
        priced = {c: t for c, t in self.totals.items() if t is not None}
        return min(priced, key=priced.get) if priced else None

    async def wait(self, code: str) -> None:
        for event in (self.all_in, self.first_done):
            if event is self.first_done and code == self._first():
                return
            try:
                await asyncio.wait_for(event.wait(), self.WAIT_S)
            except asyncio.TimeoutError:
                return

    def done(self, code: str) -> None:
        if code == self._first() or not self.all_in.is_set():
            self.first_done.set()  # also on a timeout: nobody waits on a check that is not coming


def _mode(rfq: dict) -> str:
    return rfq.get("ask") if rfq.get("ask") in ("cheapest", "fastest", "balanced") else "cheapest"


def in_eur(option: dict, fx: dict[str, float]) -> dict | None:
    """A sheet option in EUR (every line converted with the portal's last stated rate), or None if unknown."""
    currency = (option.get("currency") or "EUR").upper()
    if currency == "EUR":
        return option
    if currency not in fx:
        return None
    rate = Decimal(str(fx[currency]))
    breakdown = [{**line, "label": f"{line['label']} ({currency} × {rate})",
                  "amount": float(money(Decimal(str(line["amount"])) * rate))} for line in option["breakdown"]]
    total = float(sum(Decimal(str(line["amount"])) for line in breakdown))
    return {**option, "currency": "EUR", "total": total, "total_eur": total, "breakdown": breakdown}


def _date(ready: str | None) -> str:
    """The day the tariff must be valid: the ready date, never in the past (a past or mistyped year → today)."""
    today = date.today().isoformat()
    try:
        return max(date.fromisoformat(ready).isoformat(), today) if ready else today
    except (TypeError, ValueError):
        return today


def _sane_trucks(trucks: list[dict], actual_kg: float, cbm: float) -> tuple[list[dict], list[str]]:
    """R68: a misread EUR 45.00 for 1,494 kg won the pickup and the quote was rejected too_low. Drop bids
    under 0.05 EUR per chargeable kg, under EUR 100 AND under half the median, or more than 3x below the median; a bid without transit gets the
    median transit of the others (so it can't win the ratio pick on price alone)."""
    if not trucks:
        return trucks, []
    kg = max(actual_kg, cbm * 167)
    totals = sorted(float(t.get("total_eur") or t.get("total") or 0) for t in trucks)
    median = totals[len(totals) // 2]
    keep, odd = [], []
    for t in trucks:
        total = float(t.get("total_eur") or t.get("total") or 0)
        # no absolute floor: EUR 41.80 is a real price for 76 kg (R70, dropping it made the quote too high). The per-kg
        # floor alone would drop a normal EUR 119 for 4 t: it only counts for a two-digit bid (R68's misread EUR 45.00)
        # that is also under half of the median. A three-digit trucker price is never dropped by it.
        if (kg and total / kg < 0.05 and total < 100 and total * 2 < median) or (len(trucks) >= 3 and total * 3 < median):
            odd.append(f"{t.get('carrier')} EUR {total:,.2f}")
        else:
            keep.append(t)
    if not keep:
        return trucks, []  # all of them odd: nothing better to go on
    days = sorted(t["transit_days"] for t in keep if t.get("transit_days"))
    if days:
        mid = days[len(days) // 2]
        keep = [t if t.get("transit_days") else {**t, "transit_days": mid} for t in keep]
    return keep, odd


def _sane_air(air: list[dict], actual_kg: float, cbm: float) -> tuple[list[dict], list[str]]:
    """Mailed airline offers (often read from a PDF/txt attachment since R65) that are 3x off the median of all air
    options, or under 0.30 EUR per chargeable kg, are misreads: dropped. Sheet and portal rates are never dropped."""
    if len(air) < 3:
        return air, []
    kg = max(actual_kg, cbm * 167)
    totals = sorted(float(o.get("total_eur") or o.get("total") or 0) for o in air)
    median = totals[len(totals) // 2]
    keep, odd = [], []
    for o in air:
        total = float(o.get("total_eur") or o.get("total") or 0)
        if o.get("source") == "carrier_bid" and median and (
                total * 3 < median or total > median * 3 or (kg and total / kg < 0.30)):
            odd.append(f"{o.get('carrier')} EUR {total:,.2f}")
        else:
            keep.append(o)
    return (keep, odd) if keep else (air, [])
