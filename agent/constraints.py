"""Customer constraints in an RFQ mail, read by rules (no LLM). Round 42 was rejected `excluded_airline`; this reads the
close variants too, so the same mistake doesn't come back in other words:

- carriers the customer excludes ("do not offer Zephyr", "Lumen is not acceptable", "bitte ohne Lumen", "außer X")
- carriers the customer requires ("only Lumen Air Cargo", "nur mit Lumen", "ausschließlich Lumen")
- a maximum transit time ("transit max. 3 days", "Laufzeit höchstens 4 Tage")
- routing wishes we have no data to check (direct only, no transshipment, not via DXB, freighter only): a note

A negation counts only when it binds to the name: "We do not mind which airline, Lumen Air was great" excludes nothing.
An exclusion is remembered for the customer only when the sentence says so ("future", "any of our inquiries",
"künftig"). `CUSTOMER_CONSTRAINTS=off` restores the round-42 rule (exclusions.excluded_in) and skips the rest.
"""

import json
import os
import re
from pathlib import Path

ON = os.environ.get("CUSTOMER_CONSTRAINTS", "on").lower() != "off"
PORTS = Path(__file__).resolve().parent.parent / "backend" / "data" / "portal_ports.json"
GENERIC = {"air", "cargo", "airways", "airlines", "airline", "freight", "freightways", "lines", "logistics", "wings",
           "skylift", "skyfreight", "spedition", "transport", "transporte", "logistik", "trucking", "kurier",
           "kurierdienst", "express", "haulage", "fracht"}

_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "ein": 1, "einen": 1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7,
        "acht": 8, "neun": 9, "zehn": 10}
_N = r"(\d{1,2}|" + "|".join(_NUM) + r")"

# Words that may stand between a cue and the name: "do not [want to fly with] Lumen", "bitte keine [Angebote von] X".
_FILL = (r"(?:\s+(?:to|with|via|on|by|us|me|any|the|a|an|offer|offers|offering|use|using|quote|quotes|quoting|book|"
         r"booking|propose|include|consider|want|fly|flying|ship|shipping|send|route|choose|select|take|flights?|have|having|"
         r"rates?|again|please|kindly|airline|carrier|from|ever|go|this|shipment|"
         r"mit|über|ueber|per|bei|bitte|die|der|den|das|dem|fluggesellschaft|angebot|angebote|anbieten|nehmen|"
         r"buchen|verwenden|nutzen|fliegen|einsetzen|wieder|mehr|von)\b)*\s*")
EXCLUDE_BEFORE = re.compile(
    r"(?:\b(?:do(?:es)?\s+not|don['’]?t|doesn['’]?t|never|not|no|avoid|avoiding|exclude|excluding|except(?:\s+for)?|"
    r"other\s+than|any(?:thing|one|body)\s+but|without|instead\s+of|rather\s+than|blacklist|"
    r"nicht|nie|niemals|kein(?:e|en|er|em)?|ohne|außer|ausser|ausgenommen|statt|anstatt|anstelle\s+von|weder)\b)" + _FILL + r"$",
    re.I)
EXCLUDE_AFTER = re.compile(
    r"^\s*(?:[,;:]\s*(?:please\s+|pls\s+)?(?:do\s+not|don['’]?t)\s+(?:use|book|offer|quote|take|propose|send)\b|"
    r"not\s*(?:[.!;]|$)|"  # "Lumen is fine, Zephyr not."
    r"(?:(?:is|are)\s+)?(?:not\s+(?:acceptable|an?\s+option|wanted|allowed|permitted|approved)|"
    r"unacceptable|excluded|blacklisted|banned|a\s+no[- ]go|off\s+the\s+table|out\s+of\s+the\s+question)|"
    r"(?:should|must|may|can|shall)\s*(?:not|n['’]t)\s+be\s+(?:used|offered|quoted|booked|considered|proposed)|"
    r"(?:bitte\s+)?nicht(?:\s+(?:anbieten|verwenden|nutzen|buchen|nehmen|einsetzen|fliegen|einplanen|anfragen))?\s*"
    r"(?:[.!,;]|$)|(?:bitte\s+)?(?:ausschließen|ausschliessen)\b|ist\s+(?:für\s+uns\s+)?ausgeschlossen|"
    r"kommt\s+(?:für\s+uns\s+)?nicht\s+in\s+frage)", re.I)
REQUIRE_BEFORE = re.compile(
    r"(?:(?<!not\s)(?<!nicht\s)\b(?:only|exclusively|solely|nur|ausschließlich|ausschliesslich|lediglich)\b|"
    r"\b(?:must|has\s+to|have\s+to|needs?\s+to)\s+(?:be\s+)?(?:fly|flown|go|ship|shipped|booked|routed|moved?)\s+"
    r"(?:with|on|by|via)\b|\binsist\s+on\b|\bcontract(?:ed)?\s+carrier\s+is\b|\bmuss\s+mit\b)" + _FILL + r"$", re.I)
REQUIRE_AFTER = re.compile(r"^\s*(?:only\b|is\s+(?:mandatory|required|a\s+must)|ist\s+(?:pflicht|vorgegeben|zwingend))",
                           re.I)
LIST = re.compile(r"^\s*(?:,|/|&|\bor\b|\band\b|\bnor\b|\boder\b|\bund\b|\bnoch\b|\bsowie\b)\s*(?:\bor\b|\band\b)?\s*$",
                  re.I)
LIST_GOES_ON = re.compile(r"^\s*(?:\([A-Z0-9]{2}\))?\s*(?:,|/|&|\bor\b|\band\b|\bnor\b|\boder\b|\bund\b|\bnoch\b|"
                          r"[.!?;]|$|please\b|bitte\b|for\b|für\b)", re.I)
CODE_AFTER = re.compile(r"^\s*\(([A-Z0-9]{2})\)")
FUTURE = re.compile(r"\b(?:future|any\s+of\s+our|all\s+(?:of\s+)?our|from\s+now\s+on|going\s+forward|in\s+general|"
                    r"(?:ever|never)\s+again|any\s?more|künftig\w*|zukünftig\w*|in\s+zukunft|generell|grundsätzlich|"
                    r"ab\s+sofort|nie\s+wieder|nicht\s+mehr|alle\s+(?:unsere|weiteren)|weitere[nr]?\s+anfragen)\b",
                    re.I)

_TRANSIT = (r"(?:transit(?:\s+time)?|time\s+in\s+transit|flight\s+time|lead\s+time|delivery\s+time|"
            r"door[- ]to[- ](?:door|airport|port)|laufzeit|transitzeit|transportzeit|flugzeit|lieferzeit)")
_DAYS = r"\s*(?:calendar\s+|business\s+|working\s+|kalender|werk|arbeits)?(?:days?|tag(?:e|en)?)\b"
_STRICT = r"under|below|less\s+than|fewer\s+than|shorter\s+than|unter|weniger\s+als|kürzer\s+als|<"
_AT_MOST = (r"max(?:imum|imal)?\.?|at\s+most|up\s+to|within|no\s+(?:more|longer)\s+than|not\s+(?:more|longer)\s+than|"
            r"(?:must|should|may|can|shall)?\s*not\s+exceed|(?:mustn|shouldn)['’]?t\s+exceed|<=|≤|"
            r"höchstens|hoechstens|nicht\s+mehr\s+als|nicht\s+länger\s+als|innerhalb(?:\s+von)?|bis\s+(?:zu|maximal)")
TRANSIT = [
    re.compile(r"\b" + _TRANSIT + r"\b[^.\n;]{0,30}?(?:\b|(?=[<≤]))(" + _STRICT + "|" + _AT_MOST + r")\s*" + _N + _DAYS,
               re.I),
    re.compile(r"(?:\b|(?=[<≤]))(" + _STRICT + "|" + _AT_MOST + r")\s*" + _N + _DAYS + r"\s+(?:of\s+|in\s+)?" + _TRANSIT
               + r"\b", re.I),
    re.compile(r"\b" + _TRANSIT + r"\b[^.\n;]{0,30}?\b" + _N + _DAYS +
               r"\s+(max(?:imum|imal)?|at\s+most|or\s+less|or\s+fewer|nicht\s+überschreiten|höchstens)\b", re.I),
]
ROUTING = re.compile(
    r"\b(?:direct\s+flights?(?:\s+only)?|only\s+direct|non[- ]?stop|no\s+(?:stop[- ]?overs?|transshipments?|"
    r"transhipments?|transfers?|connections?|layovers?)|without\s+(?:a\s+|any\s+)?(?:stop[- ]?overs?|transshipment|"
    r"connections?|layovers?)|(?:not|never)\s+(?:via|through)\s+[A-Z]{3}|(?:must|has\s+to)\s+(?:go|route|fly)\s+"
    r"(?:via|through)\s+[A-Z]{3}|freighter\s+only|(?:on\s+a\s+)?passenger\s+(?:aircraft|plane)s?\s+only|"
    r"no\s+freighters?|nur\s+direkt\w*|direktflug\w*|ohne\s+(?:zwischenstopps?|umladung|umsteigen|stopp)|"
    r"keine?\s+(?:umladung|zwischenstopps?|zwischenlandung\w*)|nicht\s+(?:über|via)\s+[A-Z]{3}|nur\s+(?:mit\s+)?"
    r"frachtflugzeug\w*|nur\s+frachter)\b", re.I)
PREFER = re.compile(r"\b(?:prefer(?:ably|red)?|ideally|bevorzugt|vorzugsweise|am\s+liebsten|gerne\s+mit)\b", re.I)


def _codes() -> dict[str, str]:
    try:
        lanes = json.loads(PORTS.read_text()).get("lanes", [])
    except (OSError, ValueError):
        return {}
    return {a["name"]: a["code"] for lane in lanes for a in lane.get("airlines", []) if a.get("code")}


CODES = _codes()


def _aliases(names: list[str]) -> list[tuple[str, str, bool]]:
    """(alias, canonical name, case-sensitive), longest first: "Lumen Air Cargo", "Lumen Air", "Lumen"."""
    seen: dict[str, set[str]] = {}
    for name in names:
        words = name.split()
        for n in range(len(words), 0, -1):
            alias = " ".join(words[:n])
            if n < len(words) and (words[n - 1].lower() in GENERIC or (n == 1 and len(alias) < 4)):
                continue
            seen.setdefault(alias.lower(), (alias, set()))[1].add(name)
    out = [(alias, next(iter(owners)), " " not in alias) for alias, owners in seen.values() if len(owners) == 1]
    return sorted(out, key=lambda a: -len(a[0]))


AIRLINE_WORD = re.compile(r"\b(?:airlines?|carriers?|codes?|flights?|fluggesellschaft\w*|airways)\b", re.I)


def _mentions(sentence: str, aliases) -> list[tuple[int, int, str]]:
    """(start, end, canonical) for each carrier named in the sentence, longest alias wins, no overlaps. A bare portal
    code ("do not use LM") counts only in a sentence about airlines, so "no PL attached" is no Polaris."""
    taken, found = [], []
    if AIRLINE_WORD.search(sentence):
        aliases = [*aliases, *((code, name, True) for name, code in CODES.items())]
    for alias, name, short in aliases:
        flags = 0 if short else re.I
        pattern = re.escape(alias)
        for m in re.finditer(r"(?<![\w-])" + pattern + r"(?![\w-])", sentence, flags):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), m.end(), name))
    return sorted(found)


def _sentences(text: str) -> list[str]:
    """Split before a capital letter only, so "Transit max. 3 days" stays one sentence."""
    return [s for s in re.split(r"(?<=[.!?;])\s+(?=[A-ZÄÖÜ])|\n+", text or "") if s.strip()]


IF = re.compile(r"\b(?:if|in\s+case|unless|wenn|falls|sofern)\s*$", re.I)


def read(text: str, carriers: list[dict] | tuple) -> dict:
    """{"excluded": [names + codes], "remember": [the ones to keep for the customer], "required": [names],
    "max_transit_days": n | None, "transit_strict": bool, "notes": [routing wishes and preferences, for a person]}."""
    out = {"excluded": [], "remember": [], "required": [], "max_transit_days": None, "transit_strict": False,
           "notes": []}
    aliases = _aliases([c["name"] for c in carriers if c.get("name")])
    for sentence in _sentences(text):
        status, prev_end = None, None
        for start, end, name in _mentions(sentence, aliases):
            before, after = sentence[:start], sentence[end:]
            if prev_end is not None and status and LIST.match(sentence[prev_end:start]) and \
                    (sentence[prev_end:start].strip() != "," or LIST_GOES_ON.match(after)):
                pass  # "do not offer Zephyr, Lumen or Aurelia": the list shares the first one's cue
            elif EXCLUDE_BEFORE.search(before) or (not IF.search(before) and
                                                   EXCLUDE_AFTER.match(re.sub(r"^\s*\([A-Z0-9]{2}\)", "", after))):
                status = "excluded"
            elif REQUIRE_BEFORE.search(before) or REQUIRE_AFTER.match(re.sub(r"^\s*\([A-Z0-9]{2}\)", "", after)):
                status = "required"
            else:
                status = None
                if PREFER.search(before[-40:]):
                    out["notes"].append(f"prefers {name} (not a must: priced as usual)")
            prev_end = end
            if status == "excluded":
                names = [name] + ([m[1]] if (m := CODE_AFTER.match(after)) else []) + \
                        ([CODES[name]] if name in CODES else [])
                out["excluded"] += names
                if FUTURE.search(sentence):
                    out["remember"] += names
            elif status == "required":
                out["required"].append(name)
        if out["max_transit_days"] is None:
            for pattern in TRANSIT:
                if m := pattern.search(sentence):
                    op, n = (m[1], m[2]) if pattern is not TRANSIT[2] else (m[2], m[1])
                    days = _NUM.get(n.lower()) if not n.isdigit() else int(n)
                    if days:
                        out["max_transit_days"] = days
                        out["transit_strict"] = bool(re.fullmatch(_STRICT, op.strip(), re.I))
                    break
        if m := ROUTING.search(sentence):
            out["notes"].append(f"routing wish we can't check: \"{m.group(0)}\"")
    required = [r for r in dict.fromkeys(out["required"]) if r not in out["excluded"]]
    return {**out, "excluded": list(dict.fromkeys(out["excluded"])), "remember": list(dict.fromkeys(out["remember"])),
            "required": required, "notes": list(dict.fromkeys(out["notes"]))}


def apply(rfq: dict, found: dict, known: list[str]) -> list[str]:
    """Writes the constraints into the Rfq; returns lines for the session log."""
    lines = []
    if excluded := list(dict.fromkeys([*found["excluded"], *known])):
        rfq["excluded_airlines"] = excluded  # the backend prices without them; they're not asked for bids
        lines.append(f"Customer excluded: {', '.join(excluded)}")
    if found["required"]:
        rfq["required_carriers"] = found["required"]
        lines.append(f"Customer requires: {', '.join(found['required'])}")
    if found["max_transit_days"]:
        rfq["max_transit_days"] = found["max_transit_days"] - (0.5 if found["transit_strict"] else 0)
        lines.append(f"Transit at most {rfq['max_transit_days']:g} days")
    lines += [f"Note: {n}" for n in found["notes"]]
    return lines


def narrow(rfq: dict, options: list[dict]) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Options that keep the customer's constraints. Findings are (code, level, text); a constraint no option keeps
    leaves the options as they are and asks a person (hold)."""
    findings, kept = [], list(options)
    excluded = {str(x).lower() for x in rfq.get("excluded_airlines") or [] if x}
    if excluded:
        def named(o):
            pickup = (o.get("pickup") or {}).get("carrier") or ""
            return {(o.get("carrier") or "").lower(), (o.get("airline_code") or "").lower(), pickup.lower()} & excluded
        ok = [o for o in kept if not named(o)]
        if not ok:
            findings.append(("excluded_carrier", "hold", "Every option uses a carrier the customer excluded"))
        else:
            kept = ok
    if required := {str(x).lower() for x in rfq.get("required_carriers") or [] if x}:
        ok = [o for o in kept if (o.get("carrier") or "").lower() in required]
        if ok:
            kept = ok
            findings.append(("required_carrier", "note", f"Customer requires {', '.join(sorted(required))}"))
        else:
            findings.append(("required_carrier", "hold", f"Customer requires {', '.join(sorted(required))}: no "
                                                         f"option from them"))
    if (limit := rfq.get("max_transit_days")) is not None:
        ok = [o for o in kept if o.get("transit_days") is not None and float(o["transit_days"]) <= float(limit)]
        if ok:
            kept = ok
        else:
            findings.append(("max_transit", "hold", f"Transit at most {float(limit):g} days: no option is that fast"))
    return kept, findings
