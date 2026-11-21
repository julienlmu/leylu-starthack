"""Airlines a customer excluded: "Please do not offer Zephyr Steppe Cargo (ZS) for this shipment or for any of our future
inquiries." (round 42, rejected `excluded_airline`). Remembered per customer, because they say "future inquiries".
The regex here is free; the RFQ extraction call also lists excluded and required carriers (any language), and
rfq_agent takes the union. Truckers count too, and so do the attachments.
"""

import json
import os
import re
import threading
from pathlib import Path

# The exclusion must govern the airline: "do not offer X", "exclude X and Y", "avoid X", "ohne X", "nicht mit X".
# A negation elsewhere in the sentence ("We do not mind which airline, Lumen Air was great") excludes nothing.
# 5U escalates a trap in the next rounds (r10 xlsx -> r11 PDF), so the r42 sentence comes back reworded: German, French,
# Spanish, "blacklisted", "do not want our goods on X". The extraction call also lists them (extract.py), any language.
VERB = (r"(?:(?:please\s+)?(?:do\s+not|don'?t|never)\s+(?:offer|use|quote|book|propose|include|fly\s+with|send\s+it\s+with|"
        r"want\b[^.\n]{0,25}?\b(?:on|with|via))|"
        r"exclud\w*|avoid\w*|without|except|not\s+with|ohne|außer|ausgenommen|nicht\s+mit|keine?n?|blacklist\w*|"
        r"(?:bieten|verwenden|nutzen|buchen|nehmen|einsetzen)\s+(?:sie\s+)?(?:bitte\s+)?(?:uns\s+)?nicht|"
        r"ne\s+pas\s+(?:proposer|utiliser|réserver|prendre|offrir)|sauf|"
        r"no\s+(?:utilic\w*|usen|ofrezc\w*|reserv\w*|incluy\w*)|excepto|salvo)")
GAP = (r"(?:(?:the|us|any|airline|airlines|carrier|carriers|trucker|trucking|haulier|haulage|company|both|either|of|with|"
       r"and|or|\([A-Z0-9]{2}\)|[A-Z][\w&.\-]*)[\s,]+){0,8}?")
# The airline before the refusal: "Zephyr Steppe Cargo is not acceptable to us", "… kommt für uns nicht in Frage".
# No comma in the gap, so "Lumen Air was great, the price is not acceptable" excludes nothing.
AFTER = (r"(?:\s*\([A-Z0-9]{2}\))?[^.,\n]{0,15}?\b(?:(?:is|are)\s+(?:not|no\s+longer)\s+(?:acceptable|an\s+option|allowed|"
         r"approved|wanted|welcome|permitted)|(?:should|must|may)\s+not\s+be\s+used|(?:is|has\s+been)\s+blacklisted|"
         r"kommt\b[^.\n]{0,20}?nicht\s+in\s+frage|ist\s+ausgeschlossen|scheidet\s+aus|out\s+of\s+the\s+"
         r"(?:question|options|running|quote))")
BAD = re.compile(r"\b(?:bad|poor|negative|terrible)\s+experiences?\s+with\s+(?:the\s+)?", re.I)
OTHER = re.compile(r"\b(?:another|other|different|alternative)\s+(?:carrier|airline)|\bnot\s+again\b", re.I)
# "Please quote Lumen Air Cargo only", "we have a contract with X", "nur mit X": only those may be quoted
ONLY = (r"(?:only\s+(?:with|use|quote|offer|book|fly\s+with|work\s+with|ship\s+with)|(?:only|exclusively)\s+(?:work|ship|fly)"
        r"\s+with|exclusively\s+with|have\s+a\s+(?:contract|framework\s+agreement|rate\s+agreement)\s+with|"
        r"must\s+(?:fly|go)\s+with|nur\s+mit|ausschließlich\s+mit|uniquement\s+avec|seulement\s+avec|solo\s+con|"
        r"únicamente\s+con)")
CODE = re.compile(r"^[A-Z][A-Z0-9]$|^[0-9][A-Z]$")
NOT_A_CODE = {"DG", "UN", "EU", "US", "UK", "OK", "PC", "AM", "PM", "IT", "CM", "KG", "LB", "ID", "VAT", "PO", "NO"}
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
            if not airline:
                continue
            name = "(?i:" + re.escape(airline) + r")"
            m = (re.search("(?i:" + VERB + r")\s+" + GAP + name + r"(?:\s*\(([A-Z0-9]{2})\))?", sentence)
                 or re.search(name + r"(?:\s*\(([A-Z0-9]{2})\))?" + "(?i:" + AFTER + ")", sentence))
            bad = not m and BAD.search(sentence) and OTHER.search(sentence) and re.search(BAD.pattern + name, sentence, re.I)
            if m or bad:
                found += [airline, *([m.group(1)] if m and m.group(1) else [])]
        for name, code in NAMED.findall(sentence):  # an airline we don't list yet ("do not offer Foo Air (FA)")
            if any(name.lower() in a.lower() or a.lower() in name.lower() for a in found if len(a) > 2):
                continue  # already found as a listed airline
            if CODE.match(name) and name not in NOT_A_CODE:  # "Please don't use ZS for this one."
                found.append(name)
            elif code or any(w in name.lower() for w in ("air", "cargo", "airline", "airways", "freight", "lines")):
                found += [name.strip(), *([code] if code else [])]
    return list(dict.fromkeys(found))


def required_in(text: str, airlines: list[str]) -> list[str]:
    """Airlines the customer wants exclusively ("we only work with X", "X only", "nur mit X"): only they may be quoted."""
    found: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        for airline in airlines:
            name = "(?i:" + re.escape(airline) + r")" if airline else None
            if name and (re.search("(?i:" + ONLY + r")\s+" + GAP + name, sentence)
                         or re.search(name + r"(?:\s*\([A-Z0-9]{2}\))?\s+only\b", sentence, re.I)):
                found.append(airline)
    return list(dict.fromkeys(found))


def known_names(said: list[str] | None, names: list[str], mail_text: str = "") -> list[str]:
    """The extraction's carrier names mapped onto our list ("Meridian" → "Meridian Freightways"); a two-letter code
    stays a code (the backend matches airline_code), any other name is kept as written. With mail_text, a name the
    mail doesn't contain is dropped: an invented exclusion would drop the best option (too_high)."""
    out: list[str] = []
    for raw in said or []:
        text = (raw or "").strip()
        if not text or text.upper() in NOT_A_CODE:
            continue
        if mail_text and not re.search(r"(?<!\w)" + re.escape(text) + r"(?!\w)", mail_text, re.I):
            continue
        if CODE.match(text):
            out.append(text)
            continue
        low = text.lower()
        match = [n for n in names if len(low) > 3 and (low == n.lower() or low in n.lower() or n.lower() in low)]
        out += match[:1] or [text]
    return list(dict.fromkeys(out))


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
