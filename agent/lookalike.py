"""LOOKALIKE (default on; off = answered like any other mail): a sender address that imitates a known customer's.

R108: nordlicht.audio@… (dot) wrote as the real customer nordlicht-audio@… (hyphen): "our mailbox is down, confirm your
price for BKK to this address", no shipment data. A price or any session data sent there goes to an impostor.

A known customer = an address with a session in the CRM. The new sender has none of its own and its address is:
- strong (always): the same address once dots, hyphens, underscores, plus signs and look-alike characters (0/o, 1/l/i,
  rn/m, vv/w) are taken out, or the same local part at a domain with the same name under another ending or one letter
  off (nordlicht-audio.de → nordlicht-audio.com, nordlicht-audi0.de);
- weak (only with a red flag such as "mailbox is down", "send it to this address", "confirm your price"): one letter
  off at the same domain (anna@ vs anne@ can be two colleagues), or the same long local part at another provider
  (weidner-spielwaren@gmail.com for weidner-spielwaren@hackloop.mail; never generic mailboxes: info@, purchasing@ …).
S115: kessler-feinmechanik.mail@ wrote as kessler-feinmechanik@ ("new mail address, send the LIM offer here"): the
customer's local part with a filler word glued on (mail, email, new, neu, alt, 2 …) is strong; with any other word
(einkauf.hofmann-textilwerk@ may be a colleague) it counts only with a red flag. An unknown sender that claims a new
or broken address, asks for "the" offer / quote / booking and gives no shipment figures (no weight) is a lookalike too: a real customer's new address comes
with a request, an impostor's asks for an earlier offer. It goes to a person, nothing is sent.
A strong match gets NO reply at all (Orhun, 22 Nov) and its session is closed; a weak one with a red flag is sent
nothing either but goes to a person (it may be a real colleague). The session shows which customer it imitates.
Rules only, no LLM.
"""

import os
import re

ON = os.environ.get("LOOKALIKE", "on").lower() != "off"

ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Cyrillic letters that look Latin (а е о р с у х і ј ѕ), then the Latin look-alikes.
CYRILLIC = str.maketrans("аеорсухіјѕ", "aeopcyxijs")
GENERIC = {"info", "sales", "purchasing", "purchase", "buyer", "buying", "contact", "office", "einkauf", "logistics",
           "logistik", "export", "import", "shipping", "orders", "order", "service", "support", "admin", "mail", "hello",
           "procurement", "dispatch", "versand", "verkauf", "bestellung", "achat", "compras", "acquisti", "inkoop"}
GLYPHS = [("rn", "m"), ("vv", "w"), ("0", "o"), ("1", "l"), ("i", "l"), ("|", "l")]
FILLER = {"mail", "email", "emails", "new", "neu", "neue", "alt", "old", "official", "offiziell", "real", "secure",
          "team", "temp", "backup", "web", "online", "de", "com", "net", "eu", "gmbh", "ag", "kg", "co", "the"}
RED_FLAG = re.compile(
    r"\bnew\s+(?:e-?)?mail\s*(?:box|address|adress|account)?\b|\bneue\s+(?:e-?)?mail(?:-?adresse)?\b|"
    r"\b(?:send|reply|answer|forward|mail)\b[^.\n]{0,40}?\b(?:here|hierher|hierhin)\b|"
    r"\b(?:mail\s*box|e-?mail|inbox|server|account)\b[^.\n]{0,30}\b(?:down|not working|broken|hacked|unavailable|problems?)\b|"
    r"\b(?:to|at|on|use)\s+this\s+(?:new\s+)?(?:e-?mail\s+)?address\b|\bnew\s+e-?mail(?:\s+address)?\b|"
    r"\b(?:temporary|alternative|private|personal)\s+(?:e-?mail|address|mailbox)\b|"
    r"\b(?:confirm|resend|re-send|forward)\s+(?:us\s+|me\s+)?(?:your|the|our)\s+(?:price|quote|quotation|offer|rate|"
    r"booking|invoice)\b|\bbank\s+(?:details|account)\b|\bchanged?\s+(?:our|my)\s+(?:e-?mail|address)\b|\b(?:e-?mail|address)\s+(?:has\s+)?changed\b|"
    r"\b(?:postfach|mailserver)\b[^.\n]{0,30}\b(?:gestört|ausgefallen|kaputt|down)\b|\bdiese\s+(?:neue\s+)?adresse\b", re.I)


# "new mail address", "mailbox is down", "we changed our email": a claim only an existing customer could make.
NEW_ADDRESS = re.compile(
    r"\bnew\s+(?:e-?)?mail\s*(?:box|address|adress|account)?\b|\bneue\s+(?:e-?)?mail(?:-?adresse)?\b|"
    r"\b(?:mail\s*box|e-?mail|inbox|mail\s*server|account)\b[^.\n]{0,30}\b(?:down|not working|broken|hacked|unavailable)\b|"
    r"\bchanged?\s+(?:our|my)\s+(?:e-?mail|mail|address)\b|\b(?:e-?mail|mail)\s+(?:address\s+)?(?:has\s+)?changed\b|"
    r"\b(?:postfach|mailserver)\b[^.\n]{0,30}\b(?:gestört|ausgefallen|kaputt|down)\b", re.I)
# ... and asks for an offer, quote or booking it should already have: "send the LIM offer here", "resend our quote".
EARLIER_OFFER = re.compile(r"\b(?:send|resend|re-send|forward|confirm|share|schicken|senden)\b[^.\n]{0,30}?\b"
                           r"(?:the|our|that|this|das|unser\w*|dieses)\s+(?:[\w-]+\s+){0,2}?(?:offer|quote|quotation|"
                           r"price|rate|booking|invoice|confirmation|angebot|buchung|rechnung)\b", re.I)
WEIGHT = re.compile(r"\d[\d.,]*\s?(?:kg|kgs|kilo\w*|lbs?|pounds?|t|tons?|tonnes?)\b", re.I)
NEW_ADDRESS_CLAIM = "an existing customer (unknown sender claims a new address)"


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


_FILLER_SQUASHED = {_squash(word): word for word in FILLER}


def _glued(s_local: str, k_local: str) -> str | None:
    """The word glued before or after the customer's own local part (kessler-feinmechanik.mail → "mail"), or None."""
    k = _squash(k_local)
    if len(k) < 8 or re.split(r"[.\-_+]", k_local)[0] in GENERIC:
        return None
    parts = [p for p in re.split(r"[.\-_+]", s_local.lower()) if p]
    for cut in range(1, len(parts)):
        head, tail = "".join(parts[:cut]), "".join(parts[cut:])
        if _squash(tail) == k:
            return head
        if _squash(head) == k:
            return tail
    s = _squash(s_local)  # glued without a separator: kesslerfeinmechanikmail, kessler-feinmechanik2
    if s != k and (s.startswith(k) or s.endswith(k)):
        rest = s[len(k):] if s.startswith(k) else s[:-len(k)]
        return _FILLER_SQUASHED.get(rest) or (rest if rest.isdigit() else None)
    return None


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
    if same_local and _one_off(_squash(_name(s_domain)), _squash(_name(k_domain))) and len(_squash(_name(k_domain))) >= 6:
        return "strong"  # anna@meyer-gmbh.de vs anna@meyr-gmbh.de
    if (word := _glued(s_local, k_local)) and (word in FILLER or word.isdigit()) and (
            same_name or _one_off(_squash(_name(s_domain)), _squash(_name(k_domain)))):
        return "strong"  # S115 kessler-feinmechanik.mail@ for kessler-feinmechanik@ (a colleague's einkauf. is not)
    if s_domain == k_domain and len(k_local) >= 5 and _one_off(_squash(s_local), _squash(k_local)):
        return "weak"
    if same_local and len(k_local) >= 8 and re.split(r"[.\-_+]", k_local)[0] not in GENERIC:
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
    if flagged:  # einkauf.hofmann-textilwerk@ / hofmann-textilwerk.mail@gmail.com + "mailbox down, send it here"
        for address in sorted(known):
            local = address.split("@", 1)[0]
            if _glued(sender.split("@", 1)[0], local):
                return address
    text = f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"
    if NEW_ADDRESS.search(text) and EARLIER_OFFER.search(text) and not WEIGHT.search(text):
        return NEW_ADDRESS_CLAIM  # "new mail address, send the LIM offer here" from a sender we have never quoted
    return None


