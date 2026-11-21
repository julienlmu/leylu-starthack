"""Dangerous goods in an RFQ: the mail may say "non-dangerous" while the attached packing list says "UN1133, Class 3".

5U rejects a quote for dangerous goods that doesn't ask for the DG documents (reason dg_docs_missing, round 10).
Rules only, no LLM: UN numbers, "dangerous goods: <something>" that isn't a no, and DG classes next to DG words.
"""

import re

UN = re.compile(r"\bUN\s?-?\s?(\d{4})\b")
DG_FIELD = re.compile(r"dangerous\s+goods\s*[:|]\s*\|?\s*([^\n|]+)", re.I)
NO = re.compile(r"^\s*(no|none|n/?a|non[- ]?dangerous|keine?|nein|-|0)\b", re.I)
CLASS = re.compile(r"\bclass\s*([1-9](?:\.\d)?)\b", re.I)
DG_WORDS = re.compile(r"\b(hazardous|hazmat|flammable|corrosive|explosive|toxic|lithium|DGR|IMDG|ADR)\b", re.I)
NEGATED = re.compile(r"\b(non|not|no|kein|keine)[- ]?(dangerous|hazardous|hazmat|DG)\b", re.I)


def dg_info(*texts: str) -> str | None:
    """A short description like "UN1133, Class 3" when any text shows dangerous goods, else None."""
    text = "\n".join(t for t in texts if t)
    uns = sorted(set(UN.findall(text)))
    classes = sorted(set(CLASS.findall(text)))
    fields = [f.strip() for f in DG_FIELD.findall(text) if f.strip() and not NO.match(f)]
    words = [w for w in DG_WORDS.findall(NEGATED.sub(" ", text))]
    if not (uns or fields or (classes and words)):
        return None
    parts = [f"UN{u}" for u in uns] + [f"Class {c}" for c in classes]
    return ", ".join(parts) or (fields[0][:60] if fields else "dangerous goods")
