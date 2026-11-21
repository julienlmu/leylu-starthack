"""Dangerous goods in an RFQ: the mail may say "non-dangerous" while the attached packing list says "UN1133, Class 3".

5U rejects a quote for dangerous goods that doesn't ask for the DG documents (reason dg_docs_missing, round 10).
Rules only, no LLM: UN numbers, "dangerous goods: <something>" that isn't a no, and DG classes next to DG words.
"""

import re

from bids import to_number

UN = re.compile(r"\bUN\s?-?\s?(\d{4})\b")
# The ":" is required: a packing-list table header "Item | Dangerous goods | Gross weight" is no declaration.
DG_FIELD = re.compile(r"dangerous\s+goods\s*:\s*\|?\s*([^\n|]+)", re.I)
# "Not restricted" is the IATA wording for non-DG cargo.
NO = re.compile(r"^\s*(no|none|nil|not|false|n/?a|non[- ]?(dangerous|hazardous|dg)|keine?|nein|nicht|-|0)\b",
                re.I)
CLASS = re.compile(r"\bclass\s*([1-9](?:\.\d)?)\b", re.I)
DG_WORDS = re.compile(r"\b(hazardous|hazmat|flammable|corrosive|explosive|toxic|lithium|DGR|IMDG|ADR)\b", re.I)
LITHIUM = re.compile(r"\blithium[- ](ion|metal|batter|cell)", re.I)  # UN3480/3481/3090/3091, always DG by air
# Goods that fly as DG whatever the mail says (rounds 10 and 11: "industrial adhesives", "maintenance spray cans")
DG_GOODS = re.compile(r"\b(adhesives?|glues?|aerosols?|spray[- ]?cans?|spray paints?|perfumes?|fragrances?|solvents?|"
                      r"lacquers?|thinners?|flammable|lithium[- ]?batter(y|ies))\b", re.I)
# The class check keeps the narrow negation: "Class 2.2, non-flammable gas" is IATA's own name for a DG division.
NEGATED_DG = re.compile(r"\b(non|not|no|kein|keine)[- ]?(dangerous|hazardous|hazmat|DG)\b", re.I)
# "non-flammable", "no lithium batteries", "without lithium", "lithium-free" say the goods are NOT DG.
NEGATED = re.compile(r"\b(?:non|not|no|without|free\s+of|kein|keine|ohne)[- ]?(?:dangerous|hazardous|hazmat|DG|flammable|"
                     r"lithium(?:[- ](?:ion|metal))?(?:[- ]batter(?:y|ies)|[- ]cells?)?)\b|\blithium[- ]free\b", re.I)


def dg_info(*texts: str) -> str | None:
    """A short description like "UN1133, Class 3" when any text shows dangerous goods, else None."""
    text = "\n".join(t for t in texts if t)
    uns = sorted(set(UN.findall(text)))
    classes = sorted(set(CLASS.findall(text)))
    fields = [f.strip() for f in DG_FIELD.findall(text) if f.strip() and not NO.match(f)]
    words = [w for w in DG_WORDS.findall(NEGATED_DG.sub(" ", text))]
    lithium = LITHIUM.search(NEGATED.sub(" ", text))
    goods = DG_GOODS.search(NEGATED.sub(" ", text))
    if not (uns or fields or (classes and words) or lithium or goods):
        return None
    if lithium and not (uns or classes):
        return "lithium batteries"
    if goods and not (uns or classes or fields):
        return goods.group(0).lower()
    parts = [f"UN{u}" for u in uns] + [f"Class {c}" for c in classes]
    return ", ".join(parts) or (fields[0][:60] if fields else "dangerous goods")


TOTAL_KG = re.compile(r"total\s+gross\s+weight([^\n\d]*?)(\d[\d.,]*)\W{0,3}(lbs?\b)?", re.I)
TOTAL_CBM = re.compile(r"total\s+volume[^\n\d]*?(\d+(?:[.,]\d+)?)", re.I)
LB_KG = 0.45359237


def attachment_totals(text: str) -> tuple[float | None, float | None]:
    """(total gross kg, total cbm) as a packing list states them ("Total gross weight (kg): | 1,250"), else None."""
    kg = TOTAL_KG.search(text or "")
    cbm = TOTAL_CBM.search(text or "")
    weight = to_number(kg.group(2)) if kg else None  # "1,250" and "1.250" are 1250 kg
    if weight and (kg.group(3) or re.search(r"\blbs?\b", kg.group(1), re.I)):
        weight = round(weight * LB_KG, 1)
    return weight, float(cbm.group(1).replace(",", ".")) if cbm else None
