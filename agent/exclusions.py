"""Airlines a customer won't accept (R42: "Please do not offer Zephyr Steppe Cargo (ZS) for this shipment or for any
of our future inquiries." → rejected excluded_airline). The negation must bind to the airline itself; it is
remembered per customer only when they say it holds for future inquiries too."""
import json
import os
import re
from pathlib import Path

STORE = Path(os.environ.get("EXCLUSIONS_FILE", Path(__file__).resolve().parent / "excluded_airlines.json"))
NEG = (r"(?:\b(?:do not|don't|dont|never|please don't|bitte nicht|bitte kein\w*)\s+"
       r"(?:offer|use|quote|book|propose|consider|send|fly with|ship with|anbieten|nutzen|buchen|verwenden)"
       r"|\b(?:exclude|excluding|avoid|without|ohne|kein\w*|not with|nicht mit|nicht über|not via))")
FILLER = r"(?:\s+(?:us|me|any|anything|flights?|freight|cargo|with|via|from|on|the|an?|mit|über|von|der|die|das))*\s+"
FUTURE = re.compile(r"\b(future|any of our|all (?:of )?our|from now on|going forward|künftig\w*|zukünftig\w*|"
                    r"in zukunft|weitere\w* anfragen)\b", re.I)


def found_in_mail(body: str, carriers: list[dict] | tuple) -> list[str]:
    """Names (and the code in brackets right after them) of airlines the mail rules out."""
    out: list[str] = []
    text = body or ""
    for c in carriers:
        if c.get("kind") != "airline":
            continue
        m = re.search(NEG + FILLER + re.escape(c["name"]) + r"(?:\s*\(([A-Z0-9]{2})\))?", text, re.I)
        if m:
            out += [x for x in (c["name"], m.group(1)) if x and x not in out]
    for m in re.finditer(NEG + FILLER + r"\(?([A-Z0-9]{2})\)", text):  # only a code in brackets: "do not use (ZS)"
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def _load() -> dict:
    try:
        return json.loads(STORE.read_text())
    except (OSError, ValueError):
        return {}


def for_customer(customer: str, body: str, carriers) -> list[str]:
    """This mail's exclusions plus the ones this customer gave for future inquiries; remembers those."""
    store = _load()
    known = list(store.get((customer or "").lower(), []))
    found = found_in_mail(body, carriers)
    new = [x for x in found if x not in known]
    if new and customer and FUTURE.search(body or ""):
        store[customer.lower()] = known + new
        try:
            STORE.write_text(json.dumps(store, indent=1))
        except OSError:
            pass
    return known + new
