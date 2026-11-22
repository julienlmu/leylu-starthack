"""5U rate portal client: lanes, weight breaks, priced rates (with rate IDs) and booking. API docs: {FIVEU_BASE_URL}/docs.

Rates are rate limited: 10 per team per fixed minute (seen live; 429 + Retry-After). Ports and brackets are free.
A rate is priced in the bracket of the weight asked for, so pricing.py may also ask for the next break up; those
optional calls only run while the minute's budget keeps a reserve for the next RFQ and for re-pricing a booking.
Rate IDs live about 10 minutes (`valid_until`); answers are cached until then.
"""

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path

import httpx

SNAPSHOT = Path(__file__).parent / "data" / "portal_ports.json"
FX_FILE = Path(os.environ.get("FX_FILE", str(Path(__file__).parent / "data" / "fx.json")))  # gitignored
PORTS_TTL_S = 300  # the setup changes about once an hour; re-read the lanes every 5 min
BRACKETS_TTL_S = 600
MAX_RETRY_AFTER_S = 3  # a quote must go out within 2 min: don't wait long for the rate limit
RESERVE = int(os.environ.get("PORTAL_RESERVE", "3"))  # calls per minute kept free for must-have lookups
# The cheapest airline's next-break check may dig into the reserve down to this many calls: it is the one optional
# call that can change the quote (5U: "the best price is not always the obvious one"); one call stays free for a booking.
LEAD_RESERVE = int(os.environ.get("PORTAL_LEAD_RESERVE", "1"))


class Portal:
    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url or os.environ.get("FIVEU_BASE_URL", "https://api.start-hack.5u.ai")
        self.api_key = api_key if api_key is not None else os.environ.get("FIVEU_API_KEY", "")
        self.transport = transport
        self._http: httpx.AsyncClient | None = None
        self._ports: tuple[float, dict] | None = None
        self._brackets: dict[str, tuple[float, list[float]]] = {}
        self.fx: dict[str, float] = _load_fx()  # EUR per 1 unit of a currency, as last stated by the portal
        self.limit = asyncio.Semaphore(4)
        self.last_error: str | None = None
        self._cache: dict[tuple, dict] = {}
        self._inflight: dict[tuple, asyncio.Future] = {}  # prefetch and /api/price asking the same thing share one call
        self._budget: tuple[int, int] | None = None  # (minute, calls left) from X-RateLimit-Remaining

    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self.base_url, headers={"X-API-Key": self.api_key},
                                           timeout=8, transport=self.transport)
        return self._http

    async def airlines(self, origin: str, destination: str) -> list[dict]:
        """[{code, name}] the portal can price on this lane (live, cached; the kit snapshot if the portal is down)."""
        if self._ports is None or time.time() - self._ports[0] > PORTS_TTL_S:
            lanes = None
            if self.api_key:
                try:
                    response = await self.http().get("/v1/portal/ports")
                    response.raise_for_status()
                    lanes = response.json()["lanes"]
                except (httpx.HTTPError, KeyError, ValueError) as error:
                    self.last_error = f"ports: {error}"
            if lanes is None and self._ports is None:
                lanes = json.loads(SNAPSHOT.read_text())["lanes"]
            if lanes is not None:
                self._ports = (time.time(), {f"{l['origin']}-{l['destination']}": l["airlines"] for l in lanes})
        return self._ports[1].get(f"{origin}-{destination}".upper(), [])

    async def brackets(self, code: str) -> list[float]:
        """The airline's weight breaks in kg (a bracket runs from its break to the next). [] if unknown."""
        held = self._brackets.get(code)
        if held and time.time() - held[0] < BRACKETS_TTL_S:
            return held[1]
        try:
            response = await self.http().get("/v1/portal/brackets", params={"airline": code})
            response.raise_for_status()
            data = response.json()
            breaks = [float(b) for b in data.get("breaks_kg", [])]
        except (httpx.HTTPError, ValueError, TypeError) as error:
            self.last_error = f"brackets {code}: {error}"
            return held[1] if held else []
        self._brackets[code] = (time.time(), breaks)
        return breaks

    def calls_left(self) -> int:
        if self._budget is None or self._budget[0] != int(time.time() // 60):
            return 10
        return self._budget[1]

    async def rate(self, origin: str, destination: str, airline: str, weight_kg: float,
                   volume_cbm: float = 0, optional: bool = False, fresh: bool = False,
                   lead: bool = False) -> dict | None:
        """One priced rate (rate_id, total, currency, transit_days, valid_until, …) or None if the portal can't.

        optional=True: skipped when the minute's budget is down to the reserve (next-break checks).
        lead=True (with optional): the cheapest airline's check, skipped only at LEAD_RESERVE calls left.
        fresh=True: never from the cache (re-pricing an expired booking).
        """
        if not self.api_key:
            return None
        params = {"origin": origin.upper(), "destination": destination.upper(), "airline": airline,
                  "weight_kg": round(weight_kg, 3), "volume_cbm": round(volume_cbm, 6)}
        key = tuple(params.values())
        if not fresh and (held := self._cache.get(key)) and _later_than(held.get("valid_until"), 90):
            return held
        if optional and self.calls_left() <= (LEAD_RESERVE if lead else RESERVE):
            return None
        task = self._inflight.get(key)
        if task is None:
            self._budget = (int(time.time() // 60), self.calls_left() - 1)  # counted now: parallel checks can't overspend
            task = asyncio.ensure_future(self._fetch(params, key, airline))
            self._inflight[key] = task
            task.add_done_callback(lambda _: self._inflight.pop(key, None))
        return await asyncio.shield(task)

    async def _fetch(self, params: dict, key: tuple, airline: str) -> dict | None:
        async with self.limit:
            for attempt in range(2):
                try:
                    response = await self.http().get("/v1/portal/rates", params=params)
                except httpx.HTTPError as error:
                    self.last_error = f"rates {airline}: {error}"
                    return None
                if "X-RateLimit-Remaining" in response.headers:
                    self._budget = (int(time.time() // 60), int(response.headers["X-RateLimit-Remaining"]))
                if response.status_code == 429 and attempt == 0:
                    wait = float(response.headers.get("Retry-After", "60"))
                    if wait <= MAX_RETRY_AFTER_S:
                        await asyncio.sleep(wait)
                        continue
                if response.status_code != 200:
                    self.last_error = f"rates {airline}: {response.status_code} {response.text[:800]}"
                    return None
                rate = response.json()
                if rate.get("currency") and rate["currency"] != "EUR" and rate.get("fx_eur_per_usd"):
                    self.fx[rate["currency"]] = float(rate["fx_eur_per_usd"])
                    _save_fx(self.fx)
                self._cache[key] = rate
                return rate
        return None

    async def book(self, rate_id: str, team_reference: str) -> httpx.Response:
        """POST /v1/portal/bookings. 201 booked, 200 same retry, 404 unknown, 409 booked elsewhere, 410 expired."""
        if not self.api_key:
            raise httpx.HTTPError("FIVEU_API_KEY is not set: no portal booking")
        return await self.http().post("/v1/portal/bookings", json={"rate_id": rate_id, "team_reference": team_reference})

    def forget(self, rate_id: str) -> None:
        """A booked rate must not be quoted again from the cache."""
        self._cache = {k: v for k, v in self._cache.items() if v.get("rate_id") != rate_id}


def _later_than(iso: str | None, seconds: float) -> bool:
    """True if the ISO time is more than `seconds` from now."""
    try:
        return datetime.fromisoformat(iso).timestamp() - time.time() > seconds
    except (TypeError, ValueError):
        return False


def _load_fx() -> dict[str, float]:
    try:
        return {k: float(v) for k, v in json.loads(FX_FILE.read_text()).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def _save_fx(fx: dict[str, float]) -> None:
    try:
        temp = FX_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(fx))
        os.replace(temp, FX_FILE)
    except OSError as error:
        print(f"fx not saved: {error}")
