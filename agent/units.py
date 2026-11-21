"""Units and scope a reading got wrong, caught on the mail text (rules, no LLM call).

The model copies numbers and names their units (extract.py); code converts. A weaker read sometimes names the wrong
unit ("1,100 lbs" read as kg, "48 x 40 x 60 in" read as cm, "2 t" read as kg), the wrong scope ("240 kg each" read
as the total, "total weight 720 kg" as per piece) or splits a decimal the wrong way ("1.234,5" read as 1.2345,
"2,65 m³" as 265). Each one prices the shipment wrong by a factor, a sure reject, and some pass every plausibility
check. The mail says what is right: the unit and the "each" / "total" written next to the number the model returned.

Only a clear, single reading of the mail changes the reading: a number the mail writes with two different units,
with "each" in one place and "total" in another, or not at all is left as the model read it.
UNIT_GROUNDING=off: off (the reading is used exactly as the model returned it).
"""

import copy
import os
import re

ENABLED = os.environ.get("UNIT_GROUNDING", "on").lower() != "off"

NUMBER = re.compile(r"(?<![\d.,])\d+(?:[.,]\d+)*(?!\d)")
DIGITS = "0123456789"  # str.isdigit() is also true for "³" (m³)
WEIGHT_UNITS = {"kg": r"kgs?\b|kilo(?:gram(?:me)?)?s?\b|kilogramm\b|k\s+g\b", "lb": r"lbs?\b|pounds?\b",
                "t": r"t\b|tonnes?\b|(?:metric\s+)?tons?\b|tonnen\b"}
VOLUME_UNITS = {"m3": r"cbm\b|m3\b|m³|m\^3|cubic\s+met(?:er|re)s?\b|kubik(?:meter)?\b",
                "ft3": r"cu\.?\s?ft\b|cft\b|ft3\b|ft³|cubic\s+f(?:ee|oo)t\b",
                "l": r"lit(?:er|re)s?\b|ltrs?\b"}
DIM_UNIT = r"\s*(cm|mm|m(?![a-z0-9²³^])|inch(?:es)?\b|in\b(?!\s+(?:total|our|the|a|an|stock))|\"|”|″)"
_N = r"(\d+(?:[.,]\d+)?)"
TRIPLE = re.compile(rf"(?<![\d.,]){_N}(?:{DIM_UNIT})?\s*[x×X*]\s*{_N}(?:{DIM_UNIT})?\s*[x×X*]\s*{_N}(?:{DIM_UNIT})?", re.I)
# "240 kg each" / "240 kg per pallet" / "240 kg/pc" / "je 240 kg" / "à 240 kg" / "weight per pallet: 240 kg"
UNIT = r"(?:kgs?|kilos?|kilogramm|lbs?|pounds?|t|tonnes?|tons?)?\.?\s*\)?\s*,?\s*"
EACH_AFTER = re.compile(r"^\s*" + UNIT + r"(?:each|apiece|per\s+(?:piece|pc|pallet|crate|box|carton|case|unit|package|"
                        r"item|colli|drum|skid)|/\s*(?:pc|pcs|piece|pallet|plt|crate|box|unit|ctn)\b|je\s+(?:stück|palette|"
                        r"kiste|karton|packstück|colli)|pro\s+(?:stück|palette|kiste|karton|packstück|colli)|cada\s+uno|"
                        r"chacun|ciascuno|pro\s+st\.)", re.I)
EACH_BEFORE = re.compile(r"(?:\beach(?:\s+(?:weighing|with|of|at))?|\bje|\bà|@|\bper\s+(?:piece|pallet|crate|box|carton|"
                         r"case|unit)\s*:?|\bweight\s+(?:per|of\s+each)\s+(?:piece|pallet|crate|box|carton|case|unit)\s*:?|"
                         r"\bgewicht\s+(?:pro|je)\s+(?:stück|palette|kiste|karton)\s*:?)\s*$", re.I)
TOTAL_AFTER = re.compile(r"^\s*" + UNIT + r"(?:in\s+total|total|altogether|combined|insgesamt|gesamt|en\s+total|"
                         r"in\s+totale|au\s+total)\b", re.I)
TOTAL_BEFORE = re.compile(r"(?:\btotal(?:\s+gross)?(?:\s+weight)?|\bgross\s+weight\s+total|\bin\s+total|\baltogether|"
                          r"\binsgesamt|\bgesamt(?:gewicht)?|\btotal\s+de|\btotale)\s*:?\s*(?:of\s+)?$", re.I)


def _float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def readings(token: str) -> set[float]:
    """What a number as written can mean: "1.234,5" → {1234.5}, "1,100" → {1100, 1.1}, "2,65" → {2.65}."""
    if "." in token and "," in token:
        cut = max(token.rfind("."), token.rfind(","))
        value = _float(re.sub(r"[.,]", "", token[:cut]) + "." + token[cut + 1:])
        return {value} if value is not None else set()
    sep = "." if "." in token else "," if "," in token else None
    if sep is None:
        return {float(token)}
    groups = token.split(sep)
    if len(groups) > 2:  # 1.234.567 (thousands) or a date 24.11.2026 (no weight at all)
        return {float("".join(groups))} if all(len(g) == 3 for g in groups[1:]) else set()
    head, tail = groups
    if len(tail) == 3:  # 1.233 / 1,150: German thousands or English decimals, the model decides
        return {float(head + tail), float(f"{head}.{tail}")}
    return {float(f"{head}.{tail}")}


def misreadings(token: str) -> set[float]:
    """The other ways a reader can split the same digits ("1.234,5" → 1.2345 or 12345; "2,65" → 265)."""
    out = set()
    for candidate in (re.sub(r"[.,]", "", token), token.replace(",", ""), token.replace(".", ""),
                      token.replace(",", "."), token.replace(".", "").replace(",", ".")):
        if (value := _float(candidate)) is not None:
            out.add(value)
    return {v for v in out if not any(_same(v, r) for r in readings(token))}


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


def _occurrences(text: str, value: float) -> list[re.Match]:
    return [m for m in NUMBER.finditer(text) if any(_same(value, r) for r in readings(m.group(0)))]


def _after(text: str, m: re.Match) -> str:
    rest = text[m.end():m.end() + 40]
    return rest[:next((i for i, c in enumerate(rest) if c in DIGITS), len(rest))]


def _before(text: str, m: re.Match) -> str:
    start = max(0, m.start() - 45)
    head = text[start:m.start()]
    last = max((i for i, c in enumerate(head) if c in DIGITS), default=-1)
    return head[last + 1:]


def _unit_after(text: str, m: re.Match, units: dict[str, str]) -> str | None:
    after = text[m.end():m.end() + 40]  # not cut at the next digit: "2.5 m3" keeps its 3
    for name, pattern in units.items():
        if re.match(rf"\s*(?:{pattern})", after, re.I):
            return name
    return None


def _values(raw: dict) -> list[tuple[dict, str]]:
    """(holder, key) of every number the reading copied from the mail."""
    found = [(raw, "volume")]
    for p in raw.get("pieces") or []:
        found += [(p, k) for k in ("weight", "length", "width", "height", "volume")]
    return [(h, k) for h, k in found if isinstance(h.get(k), (int, float)) and not isinstance(h.get(k), bool)]


def _decimals(raw: dict, text: str, notes: list[str]) -> None:
    """A weight or volume the mail doesn't write, but one of its weights or volumes split the wrong way gives: the
    right split ("1.234,5 kg" read as 1.2345). Only a number written with its unit counts (never "EUR 7,20")."""
    tokens = list(NUMBER.finditer(text))
    for holder, key in _values(raw):
        if key not in ("weight", "volume"):
            continue
        value, units = float(holder[key]), WEIGHT_UNITS if key == "weight" else VOLUME_UNITS
        if any(_same(value, r) for t in tokens for r in readings(t.group(0))):
            continue
        right = {r for t in tokens if any(_same(value, w) for w in misreadings(t.group(0)))
                 and _unit_after(text, t, units) for r in readings(t.group(0))}
        if len(right) == 1:
            holder[key] = fixed = right.pop()
            notes.append(f"{value:g} → {fixed:g} (as written in the mail)")


def _weight_unit(raw: dict, text: str, notes: list[str]) -> None:
    units = {_unit_after(text, m, WEIGHT_UNITS) for p in raw.get("pieces") or [] if p.get("weight")
             for m in _occurrences(text, float(p["weight"]))} - {None}
    if len(units) == 1 and (unit := units.pop()) != raw.get("weight_unit"):
        notes.append(f"weight unit {raw.get('weight_unit')} → {unit} (as written next to the weight)")
        raw["weight_unit"] = unit


def _volume_unit(raw: dict, text: str, notes: list[str]) -> None:
    volumes = [float(v) for v in [raw.get("volume")] + [p.get("volume") for p in raw.get("pieces") or []] if v]
    units = {_unit_after(text, m, VOLUME_UNITS) for v in volumes for m in _occurrences(text, v)} - {None}
    if len(units) == 1 and (unit := units.pop()) != (raw.get("volume_unit") or "m3"):
        notes.append(f"volume unit {raw.get('volume_unit')} → {unit} (as written next to the volume)")
        raw["volume_unit"] = unit


def _dim_unit(raw: dict, text: str, notes: list[str]) -> None:
    dims = [(float(p["length"]), float(p["width"]), float(p["height"])) for p in raw.get("pieces") or []
            if p.get("length") and p.get("width") and p.get("height")]
    if not dims:
        return
    units = set()
    for m in TRIPLE.finditer(text):
        values = [readings(m.group(i)) for i in (1, 3, 5)]
        if not any(all(any(_same(d, r) for r in rs) for d, rs in zip(triple, values)) for triple in dims):
            continue
        for u in (m.group(2), m.group(4), m.group(6)):
            if u:
                u = u.lower()
                units.add("in" if u.startswith("in") or u in ('"', "”", "″") else u)
    if len(units) == 1 and (unit := units.pop()) != raw.get("dim_unit"):
        notes.append(f"dimension unit {raw.get('dim_unit')} → {unit} (as written next to the dimensions)")
        raw["dim_unit"] = unit


CURRENCY_BEFORE = re.compile(r"(?:EUR|€|USD|US\$|\$|CHF|GBP|£)\s*$", re.I)
CURRENCY_AFTER = re.compile(r"^\s*(?:EUR|€|USD|\$|CHF|GBP|£|euros?|dollars?|francs?)(?![a-z])", re.I)


def _is_weight(text: str, m: re.Match) -> bool:
    """This occurrence is a weight: a weight unit right after it and no currency next to it ("4 pallets 250 kg,
    EUR 250 per pallet handling": only the first 250 is a weight)."""
    if CURRENCY_BEFORE.search(text[max(0, m.start() - 5):m.start()]) or CURRENCY_AFTER.match(text[m.end():m.end() + 9]):
        return False
    return _unit_after(text, m, WEIGHT_UNITS) is not None


def _scope(raw: dict, text: str, notes: list[str]) -> None:
    for p in raw.get("pieces") or []:
        if not p.get("weight") or (p.get("count") or 1) <= 1:
            continue
        said = set()
        for m in [m for m in _occurrences(text, float(p["weight"])) if _is_weight(text, m)]:
            after, before = _after(text, m), _before(text, m)
            if EACH_AFTER.search(after) or EACH_BEFORE.search(before):
                said.add(False)
            if TOTAL_AFTER.search(after) or TOTAL_BEFORE.search(before):
                said.add(True)
        if len(said) == 1 and (total := said.pop()) != p.get("weight_is_total"):
            notes.append(f"{p['weight']:g} is {'the total' if total else 'per piece'} (as written in the mail)")
            p["weight_is_total"] = total


def ground(raw: dict, mail: dict) -> dict:
    """The reading with units and scope set to what the mail writes next to each number. Never raises."""
    if not ENABLED or not isinstance(raw, dict):
        return raw
    try:
        text = f"{mail.get('subject') or ''}\n{mail.get('body') or ''}"
        fixed, notes = copy.deepcopy(raw), []
        _decimals(fixed, text, notes)
        _weight_unit(fixed, text, notes)
        _volume_unit(fixed, text, notes)
        _dim_unit(fixed, text, notes)
        _scope(fixed, text, notes)
    except Exception as error:  # a rule must never cost the reading
        print(f"unit grounding skipped: {type(error).__name__}: {error}")
        return raw
    if notes:
        fixed["unit_notes"] = notes
    return fixed


# UNIT_ASK (rfq_agent): a weight, dimensions or a volume the mail writes without any unit for it ("gross weight 715",
# "dims 120x80x100") is never priced on a guessed unit. These rules say which one is unitless and read the answer.
# A unit word anywhere in the mail or its attachments counts as given: "pallet 1: 300 kg, pallet 2: 415" is kg.
_A, _Z = r"(?<![a-zà-ÿ])", r"(?![a-zà-ÿ])"
ANSWER = {"weight": {"kg": _A + r"(?:kgs?|kilo\w*)" + _Z + r"|公斤|千克|キロ|кг",
                     "lb": _A + r"(?:lbs?|pounds?|pfund|livres?|libras?)" + _Z,
                     "t": _A + r"(?:tonnes?|tons?|tonnen|toneladas?|tonnellate)" + _Z},
          "dims": {"cm": _A + r"(?:cms?|centim\w*|zentim\w*)" + _Z + r"|厘米|公分|センチ|см",
                   "mm": _A + r"(?:mm|millim\w*)" + _Z, "m": _A + r"(?:met(?:er|re)s?)" + _Z,
                   "in": _A + r"(?:inch(?:es)?|zoll|pouces?|pulgadas?|polegadas?)" + _Z + r"|″"},
          "volume": {"m3": _A + r"(?:cbm|m3|m\^3|cubic\s+met\w*|kubik\w*)" + _Z + r"|m³|立方米",
                     "ft3": _A + r"(?:ft3|cu\.?\s?ft|cft|cuft|cbf|cubic\s+f(?:ee|oo)t)" + _Z + r"|ft³",
                     "l": _A + r"(?:lit(?:er|re)s?|ltrs?)" + _Z}}
SYSTEM = {"metric": {"weight": "kg", "dims": "cm", "volume": "m3"},
          "imperial": {"weight": "lb", "dims": "in", "volume": "ft3"}}
WEIGHT_WORD = re.compile("|".join(ANSWER["weight"].values()), re.I)
DIM_WORD = re.compile("|".join(list(ANSWER["dims"].values())[:3]) + "|" + _A + r"(?:inch(?:es)?|zoll|pouces?|"
                      r"pulgadas?|ft|feet|foot)" + _Z + r"|\(\s*(?:in|m)\s*\)|\bin\s+m\b", re.I)
VOLUME_WORD = re.compile("|".join(ANSWER["volume"].values()) + "|" + _A + r"(?:cubic|cúbicos?)" + _Z + r"|立方", re.I)
VOLUME_LABEL = re.compile(r"(?:volume|vol\.?|volumen|cubage|volym|objętość|objem|体积|容積)\s*[:=]?\s*(?:of\s+|ca\.?\s*|"
                          r"approx\.?\s*|about\s*|~\s*)?$", re.I)


def _first(text: str, values: list[float], near=None) -> str | None:
    """The first number in the text that is one of the values (with near: that label right before it)."""
    for v in values:
        for m in _occurrences(text, v):
            if near is None or near.search(text[max(0, m.start() - 30):m.start()]):
                return m.group(0)
    return None


def unitless(raw: dict | None, text: str) -> dict:
    """{"weight" | "dims" | "volume": {"unit": the unit the reading assumed, "said": the number as written}} for each
    quantity the reading has, the text writes, and the text gives no unit for anywhere. Never raises."""
    if not isinstance(raw, dict):
        return {}
    try:
        out, pieces = {}, raw.get("pieces") or []
        weights = [float(p["weight"]) for p in pieces if isinstance(p.get("weight"), (int, float)) and p["weight"]]
        tons = any(_unit_after(text, m, {"t": WEIGHT_UNITS["t"]}) for m in NUMBER.finditer(text))  # "2 t"
        if weights and not tons and not WEIGHT_WORD.search(text) and (said := _first(text, weights)):
            out["weight"] = {"unit": raw.get("weight_unit") or "kg", "said": said}
        volumes = [float(v) for v in [raw.get("volume")] + [p.get("volume") for p in pieces]
                   if isinstance(v, (int, float)) and v]
        if volumes and not VOLUME_WORD.search(text) and (said := _first(text, volumes, VOLUME_LABEL)):
            out["volume"] = {"unit": raw.get("volume_unit") or "m3", "said": said}
        dims = [(float(p["length"]), float(p["width"]), float(p["height"])) for p in pieces
                if p.get("length") and p.get("width") and p.get("height")]
        if dims and not DIM_WORD.search(text) and (not volumes or "volume" in out):  # a volume with its unit decides
            for m in TRIPLE.finditer(text):
                values = [readings(m.group(i)) for i in (1, 3, 5)]
                if any(all(any(_same(d, r) for r in rs) for d, rs in zip(t, values)) for t in dims):
                    if not any(m.group(i) for i in (2, 4, 6)):
                        out["dims"] = {"unit": raw.get("dim_unit") or "cm", "said": m.group(0).strip(),
                                       "volume_from_dims": not volumes}
                    break
        return out
    except Exception as error:  # a rule must never cost the quote
        print(f"unit ask skipped: {type(error).__name__}: {error}")
        return {}


def answered(text: str, kinds) -> dict:
    """The one unit the customer's answer names for each kind ("kg", "in cm", "metric"); unclear kinds are left out."""
    out = {}
    for kind in kinds:
        found = {u for u, p in ANSWER[kind].items() if re.search(p, text, re.I)}
        found |= {s[kind] for name, s in SYSTEM.items() if re.search(rf"\b{name}\b", text, re.I)}
        if len(found) == 1:
            out[kind] = found.pop()
    return out
