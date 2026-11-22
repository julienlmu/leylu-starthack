"""PROTOTYPE, TEST ENVIRONMENT ONLY — portal rates from 5U's portal web page while the rate API is down (503).

PERMISSION: 5U gave us this code — the NopeCHA browser extension, https://github.com/NopeCHALLC/nopecha-extension —
and explicitly allowed us to use it for our project, because the CAPTCHA on the portal web page was put into the test
environment by mistake (5U, 22 Nov 2026). It is for the test environment only, never for the final version.
Off by default: PORTAL_WEB=on turns it on.

What it does: opens the portal web page in Chromium (Playwright) with the NopeCHA extension loaded (it solves the
CAPTCHA 5U put there by mistake), fills in lane, airline and weight, and reads the all-in price and the transit days
from the page. No LLM, never books anything: the rates go into pricing like a rate a person typed in.

Setup on the live Mac (once):
  1. NopeCHA's Chromium build: download it from https://github.com/NopeCHALLC/nopecha-extension/releases, unzip it,
     set PORTAL_WEB_EXTENSION=/path/to/the/unzipped/folder (the folder with manifest.json).
  2. .env: NOPECHA_KEY=<key> (never commit it), PORTAL_WEB_URL=<the portal web page's URL>, PORTAL_WEB=on.
  3. Browser: `cd agent && uv run --with playwright python -m playwright install chromium`.
  4. Run the agent with Playwright available: `uv run --with playwright --env-file ../.env python main.py`.
  Selectors: the defaults guess common field names; set PORTAL_WEB_FIELDS (JSON, see FIELDS) once the real page is
  known. The price/transit are read from the page text, so they need no selector.
"""
import json
import os
import re
import tempfile
import time

ON = os.environ.get("PORTAL_WEB", "off").lower() == "on"
URL = os.environ.get("PORTAL_WEB_URL", "")
EXTENSION = os.environ.get("PORTAL_WEB_EXTENSION", "")
KEY = os.environ.get("NOPECHA_KEY", "")
BUDGET_S = float(os.environ.get("PORTAL_WEB_BUDGET_S", "60"))  # all lookups of one RFQ together
HEADLESS = os.environ.get("PORTAL_WEB_HEADLESS", "off").lower() == "on"  # extensions need a real (or "new") headless
FIELDS = {"origin": "[name=origin]", "destination": "[name=destination]", "airline": "[name=airline]",
          "weight_kg": "[name=weight_kg]", "volume_cbm": "[name=volume_cbm]", "submit": "button[type=submit]"}
FIELDS.update(json.loads(os.environ.get("PORTAL_WEB_FIELDS") or "{}"))
PRICE = re.compile(r"\b(EUR|USD|€|\$)\s*([\d.,']+\d)|([\d.,']+\d)\s*(EUR|USD|€)", re.I)
TRANSIT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:days?|d)\b", re.I)
RATE_ID = re.compile(r"\bR-[A-Za-z0-9_-]{8,40}\b")


def ready() -> str | None:
    """Why it can't run, or None."""
    if not ON:
        return "PORTAL_WEB is off"
    missing = [n for n, v in (("PORTAL_WEB_URL", URL), ("PORTAL_WEB_EXTENSION", EXTENSION), ("NOPECHA_KEY", KEY)) if not v]
    return f"missing {', '.join(missing)}" if missing else None


def _number(raw: str) -> float:
    raw = raw.replace("'", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+[.,]\d{2}", raw):
        return float(re.sub(r"[.,]", "", raw[:-3]) + "." + raw[-2:])
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        return float(re.sub(r"[.,]", "", raw))
    return float(raw.replace(",", "."))


def read_rate(text: str) -> dict | None:
    """{"total", "currency", "transit_days", "rate_id"} from the result page's text; None if no price is shown."""
    m = PRICE.search(text or "")
    if not m:
        return None
    currency = (m.group(1) or m.group(4)).upper().replace("€", "EUR").replace("$", "USD")
    total = _number(m.group(2) or m.group(3))
    transit = TRANSIT.search(text)
    rate_id = RATE_ID.search(text)
    return {"total": total, "currency": currency, "transit_days": _number(transit.group(1)) if transit else None,
            "rate_id": rate_id.group(0) if rate_id else None}


def rates(origin: str, destination: str, airlines: list[str], weight_kg: float, volume_cbm: float = 0.0) -> list[dict]:
    """One option per airline the page priced (carrier-bid shape, source "portal_web"). [] on any failure."""
    if ready() or not airlines:
        return []
    try:
        from playwright.sync_api import sync_playwright  # only here: the default install has no Playwright
    except ImportError:
        print("portal_web: Playwright not installed (run with `uv run --with playwright`)")
        return []
    out, deadline = [], time.monotonic() + BUDGET_S
    args = [f"--disable-extensions-except={EXTENSION}", f"--load-extension={EXTENSION}"]
    if HEADLESS:
        args.append("--headless=new")
    with tempfile.TemporaryDirectory() as profile, sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(profile, headless=False, args=args)
        try:
            page = browser.new_page()
            page.goto(f"https://nopecha.com/setup#{KEY}")  # NopeCHA's documented way to give the extension its key
            for airline in airlines:
                left = deadline - time.monotonic()
                if left < 5:
                    print(f"portal_web: budget used up, {airline} not looked up")
                    break
                try:
                    page.goto(URL, timeout=left * 1000)
                    values = {"origin": origin, "destination": destination, "airline": airline,
                              "weight_kg": f"{weight_kg:g}", "volume_cbm": f"{volume_cbm or 0:g}"}
                    for field, value in values.items():
                        if page.locator(FIELDS[field]).count():
                            page.fill(FIELDS[field], value)
                    page.click(FIELDS["submit"], timeout=left * 1000)  # the extension solves the CAPTCHA meanwhile
                    page.wait_for_function(f"/{PRICE.pattern.replace('/', '')}/i.test(document.body.innerText)",
                                           timeout=max(1.0, deadline - time.monotonic()) * 1000)
                    rate = read_rate(page.inner_text("body"))
                except Exception as error:  # one airline failing never stops the others
                    print(f"portal_web: {airline}: {type(error).__name__}: {error}")
                    continue
                if rate:
                    out.append({"source": "portal_web", "leg": "air", "carrier": airline, **rate})
        finally:
            browser.close()
    return out
