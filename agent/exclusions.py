"""Airlines a customer won't accept (R42: "Please do not offer Zephyr Steppe Cargo (ZS) for this shipment or for any
of our future inquiries." → rejected excluded_airline). Found in the mail, remembered per customer address."""
import json
import os
import re
from pathlib import Path

STORE = Path(os.environ.get("EXCLUSIONS_FILE", Path(__file__).resolve().parent / "excluded_airlines.json"))
NOT_WANTED = re.compile(r"\b(do not|don't|dont|please don't|never|no longer|not)\s+(?:\w+\s+){0,2}?"
                        r"(offer|use|book|quote|propose|send|fly|ship|want|accept|consider)\b|"
                        r"\b(exclude\w*|avoid\w*|without|except|blacklist\w*|bitte nicht|keine?n?|nicht mit|"
                        r"ausgeschlossen|ausschließen|ausschliessen)\b", re.I)
CODE = re.compile(r"\(([A-Z0-9]{2})\)|\b(?:code|airline code|iata)\s*:?\s*([A-Z0-9]{2})\b")


def found_in_mail(body: str, carriers: list[dict] | tuple) -> list[str]:
    """Names (and their codes in brackets) of airlines a sentence of the mail rules out."""
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?\n])\s+", body or ""):
        if not NOT_WANTED.search(sentence):
            continue
        low = sentence.lower()
        for c in carriers:
            if c.get("kind") == "airline" and c["name"].lower() in low and c["name"] not in out:
                out.append(c["name"])
        for m in CODE.finditer(sentence):
            code = (m.group(1) or m.group(2)).upper()
            if code not in out:
                out.append(code)
    return out


def _load() -> dict:
    try:
        return json.loads(STORE.read_text())
    except (OSError, ValueError):
        return {}


def for_customer(customer: str, body: str, carriers) -> list[str]:
    """This mail's exclusions plus the ones this customer gave before; remembers new ones."""
    store = _load()
    known = list(store.get((customer or "").lower(), []))
    new = [x for x in found_in_mail(body, carriers) if x not in known]
    if new and customer:
        store[customer.lower()] = known + new
        try:
            STORE.write_text(json.dumps(store, indent=1))
        except OSError:
            pass
    return known + new
