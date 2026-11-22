"""LOOKALIKE (default on; off = answered like any other mail): a sender address that imitates a known customer's.

R108: nordlicht.audio@… (dot) wrote as the real customer nordlicht-audio@… (hyphen): "our mailbox is down, confirm your
price for BKK to this address", no shipment data. A price or any session data sent there goes to an impostor.

A known customer = an address with a session in the CRM. The new sender has none of its own and its address is:
- strong (always): the same address once dots, hyphens, underscores, plus signs and look-alike characters (0/o, 1/l/i,
  rn/m, vv/w) are taken out, or the same local part at a domain with the same name under another ending or one letter
  off (nordlicht-audio.de → nordlicht-audio.com, nordlicht-audi0.de);
- weak (only with a red flag such as "mailbox is down", "send it to this address", "confirm your price"): one letter
  off at the same domain (anna@ vs anne@ can be two colleagues).
Such a mail gets a short polite decline with no price, no lane, no reference and not the real address, and nothing
else; the session shows which customer it imitates. Rules only, no LLM.
"""

import os
import re

ON = os.environ.get("LOOKALIKE", "on").lower() != "off"

ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Cyrillic letters that look Latin (а е о р с у х і ј ѕ), then the Latin look-alikes.
CYRILLIC = str.maketrans("аеорсухіјѕ", "aeopcyxijs")
GLYPHS = [("rn", "m"), ("vv", "w"), ("0", "o"), ("1", "l"), ("i", "l"), ("|", "l")]
RED_FLAG = re.compile(
    r"\b(?:mail\s*box|e-?mail|inbox|server|account)\b[^.\n]{0,30}\b(?:down|not working|broken|hacked|unavailable|problems?)\b|"
    r"\b(?:to|at|on|use)\s+this\s+(?:new\s+)?(?:e-?mail\s+)?address\b|\bnew\s+e-?mail(?:\s+address)?\b|"
    r"\b(?:temporary|alternative|private|personal)\s+(?:e-?mail|address|mailbox)\b|"
    r"\b(?:confirm|resend|re-send|forward)\s+(?:us\s+|me\s+)?(?:your|the|our)\s+(?:price|quote|quotation|offer|rate|"
    r"booking|invoice)\b|\bbank\s+(?:details|account)\b|\bchanged?\s+(?:our|my)\s+(?:e-?mail|address)\b|"
    r"\b(?:postfach|mailserver)\b[^.\n]{0,30}\b(?:gestört|ausgefallen|kaputt|down)\b|\bdiese\s+(?:neue\s+)?adresse\b", re.I)


def _address(text: str | None) -> str:
    found = ADDRESS.search(text or "")
    return found.group(0).lower() if found else (text or "").strip().lower()


def _squash(text: str) -> str:
    text = re.sub(r"[.\-_+]", "", text.lower().translate(CYRILLIC))
    for old, new in GLYPHS:
        text = text.replace(old, new)
    return text


def _name(domain: str) -> str:
    """nordlicht-audio.co.uk → nordlicht-audio (the part a customer would recognise)."""
    parts = domain.split(".")
    while len(parts) > 1 and (len(parts[-1]) <= 3 or parts[-1] in ("info", "mail", "email")):
        parts = parts[:-1]
    return ".".join(parts)


def _one_off(a: str, b: str) -> bool:
    """Edit distance exactly 1 (one letter added, dropped, changed, or two neighbours swapped)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]]
                                  and a[diff[1]] == b[diff[0]])
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def strength(sender: str, known: str) -> str | None:
    """"strong" / "weak" when `sender` imitates `known`, else None (the same address is never a lookalike)."""
    sender, known = _address(sender), _address(known)
    if sender == known or "@" not in sender or "@" not in known:
        return None
    (s_local, s_domain), (k_local, k_domain) = sender.split("@", 1), known.split("@", 1)
    same_local = _squash(s_local) == _squash(k_local)
    same_name = _squash(_name(s_domain)) == _squash(_name(k_domain))
    if same_local and same_name:
        return "strong"  # nordlicht.audio@ vs nordlicht-audio@, nordlicht-audio.com vs .de, ANNA@ vs anna@ excluded above
    if same_local and _one_off(_squash(_name(s_domain)), _squash(_name(k_domain))) and len(_name(k_domain)) >= 5:
        return "strong"  # anna@meyer-gmbh.de vs anna@meyr-gmbh.de
    if s_domain == k_domain and len(k_local) >= 5 and _one_off(_squash(s_local), _squash(k_local)):
        return "weak"
    if same_local and len(k_local) >= 8:
        return "weak"  # nordlicht-audio@gmail.com "our mailbox is down, use this address": a red flag needed
    return None


def imitated(mail: dict, customers: list[str]) -> str | None:
    """The known customer address this mail's sender imitates, or None."""
    if not ON:
        return None
    sender = _address(mail.get("from"))
    known = {_address(c) for c in customers if c}
    if not sender or sender in known:
        return None  # a known customer (or one that already has a session of its own) is themselves
    flagged = bool(RED_FLAG.search(f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"))
    for address in sorted(known):
        level = strength(sender, address)
        if level == "strong" or (level == "weak" and flagged):
            return address
    return None


def decline_text() -> str:
    return ("Hello,\n\nthank you for your message. For your security we only send prices, bookings and shipment details "
            "to the email address we have on file for your company, and we can't confirm anything to a new or "
            "different address.\n\nPlease write to us from your usual address and I'll take care of it right away.\n\n"
            "Best regards,\nLena Hartmann, Leylü Air Freight")
