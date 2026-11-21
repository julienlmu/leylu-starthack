"""Airlines a customer excluded: "Please do not offer Zephyr Steppe Cargo (ZS) for this shipment or for any of our future
inquiries." (round 42, rejected `excluded_airline`). No LLM. Remembered per customer, because they say "future inquiries".
"""

import json
import os
import re
import threading
from pathlib import Path

# An airline counts as excluded only in a sentence that excludes something, never on a plain mention ("Lumen was great").
EXCLUDE = re.compile(r"\b(?:do not|don'?t|never|not (?:want|use|offer|quote|book|propose)|no longer|exclud\w*|avoid\w*|"
                     r"blacklist\w*|nicht|keine?n?|ohne|außer|ausgenommen|ne pas|no (?:ofrezcan|usen))\b", re.I)
NAMED = re.compile(r"\b(?:offer|use|quote|book|propose|include|anbieten|nehmen)\s+([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4})"
                   r"(?:\s*\(([A-Z0-9]{2})\))?")
CODE = re.compile(r"\(([A-Z0-9]{2})\)")
STORE = Path(os.environ.get("EXCLUSIONS_FILE", ".exclusions.json"))
_lock = threading.Lock()


def excluded_in(text: str, airlines: list[str]) -> list[str]:
    """Airline names (from our lists) and codes the mail excludes, e.g. ["Zephyr Steppe Cargo", "ZS"]."""
    found: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        if not EXCLUDE.search(sentence):
            continue
        low = sentence.lower()
        found += [a for a in airlines if a and a.lower() in low]
        for name, code in NAMED.findall(sentence):  # an airline we don't list yet ("do not offer Foo Air (FA)")
            if code or any(w in name.lower() for w in ("air", "cargo", "airline", "airways", "freight", "lines")):
                found.append(name.strip())
        found += CODE.findall(sentence)
    return list(dict.fromkeys(found))


def known(customer: str) -> list[str]:
    try:
        return json.loads(STORE.read_text()).get((customer or "").lower(), [])
    except (OSError, ValueError):
        return []


def remember(customer: str, names: list[str]) -> list[str]:
    """Adds names to the customer's exclusions; returns all of them."""
    with _lock:
        try:
            data = json.loads(STORE.read_text())
        except (OSError, ValueError):
            data = {}
        key = (customer or "").lower()
        data[key] = list(dict.fromkeys([*data.get(key, []), *names]))
        tmp = STORE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        tmp.replace(STORE)
        return data[key]
