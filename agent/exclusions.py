"""Airlines a customer excluded: "Please do not offer Zephyr Steppe Cargo (ZS) for this shipment or for any of our future
inquiries." (round 42, rejected `excluded_airline`). No LLM. Remembered per customer, because they say "future inquiries".
"""

import json
import os
import re
import threading
from pathlib import Path

# The exclusion must govern the airline: "do not offer X", "exclude X and Y", "avoid X", "ohne X", "nicht mit X".
# A negation elsewhere in the sentence ("We do not mind which airline, Lumen Air was great") excludes nothing.
VERB = (r"(?:(?:please\s+)?(?:do\s+not|don'?t|never)\s+(?:offer|use|quote|book|propose|include|fly\s+with|send\s+it\s+with)|"
        r"exclud\w*|avoid\w*|without|except|not\s+with|ohne|außer|ausgenommen|nicht\s+mit|keine?n?)")
GAP = r"(?:(?:the|us|any|airline|airlines|carrier|both|either|of|with|and|or|[A-Z][\w&.\-]*)[\s,]+){0,8}?"
# Only the verb ignores case: names are capitalised words, so "Nova Atlas Cargo." never runs into "is fine".
NAMED = re.compile("(?i:" + VERB + r")\s+(?:the\s+)?([A-Z][\w&\-]*(?:\s+[A-Z][\w&\-]*){0,4})(?:\s*\(([A-Z0-9]{2})\))?")
# "… or for any of our future inquiries": only then is it remembered for the customer's next RFQs
FUTURE = re.compile(r"\b(?:future|from now on|any of our|anymore|any more|again|always|in general|künftig|zukünftig|"
                    r"in zukunft|ab sofort|grundsätzlich)\b", re.I)
STORE = Path(os.environ.get("EXCLUSIONS_FILE", ".exclusions.json"))
_lock = threading.Lock()


def excluded_in(text: str, airlines: list[str]) -> list[str]:
    """Airline names (from our lists) and their codes that the mail excludes, e.g. ["Zephyr Steppe Cargo", "ZS"]."""
    found: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        for airline in airlines:
            if airline and (m := re.search("(?i:" + VERB + r")\s+" + GAP + "(?i:" + re.escape(airline) + r")"
                                           r"(?:\s*\(([A-Z0-9]{2})\))?", sentence)):
                found += [airline, *([m.group(1)] if m.group(1) else [])]
        for name, code in NAMED.findall(sentence):  # an airline we don't list yet ("do not offer Foo Air (FA)")
            if any(name.lower() in a.lower() or a.lower() in name.lower() for a in found if len(a) > 2):
                continue  # already found as a listed airline
            if code or any(w in name.lower() for w in ("air", "cargo", "airline", "airways", "freight", "lines")):
                found += [name.strip(), *([code] if code else [])]
    return list(dict.fromkeys(found))


def for_future(text: str) -> bool:
    return bool(FUTURE.search(text or ""))


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
