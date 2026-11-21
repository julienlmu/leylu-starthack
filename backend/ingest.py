"""Tariff ingestion: an airline's tariff file (xlsx, pdf, docx, txt, csv) → a sheet in the shape of data/tariffs.json.

No LLM: one rule-based parser for the layouts seen in the start kit (rows per lane, a block per origin, or a vertical
block per lane; surcharges inline or as "LANE: fuel X per kg, security Y per kg" lines). Images (Danube's photos)
can't be read here: they come back as an error so a person enters them.
"""

import csv
import io
import re
from datetime import date, datetime

ORIGINS = {"CGN", "DUS", "FRA", "HAM", "MUC", "STR"}  # every pickup zone maps to one of these (data/pickup_zones.csv)
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)?")
LANE_DASH = re.compile(r"\b([A-Z]{3})\s*-\s*([A-Z]{3})\b")                   # CGN-SYD
LANE_TO = re.compile(r"\(([A-Z]{3})\)\s+to\s+[^()]*\(([A-Z]{3})\)")           # Cologne (CGN) to Lagos (LOS)
LANE_ARROW = re.compile(r"\b([A-Z]{3})\b[A-Za-zÀ-ÿ .'-]*>\s*([A-Z]{3})\b[A-Za-zÀ-ÿ .'-]*")  # CGN Cologne > DEL Delhi
SURCHARGE = re.compile(r"fuel\s+(?:EUR\s+)?(\d+(?:[.,]\d+)?)\s+per\s+kg,\s*security\s+(?:EUR\s+)?(\d+(?:[.,]\d+)?)", re.I)
BREAK = re.compile(r"(?<![\w.,+-])([-+])(\d+)(?![\w.,])|from\s+(\d+)\s*kg|(\d+)\s*kg\s*\+")


class TariffError(ValueError):
    pass


def parse_tariff(filename: str, content: bytes) -> dict:
    lines = extract_lines(filename, content)
    sheet = _parse(lines)
    sheet["file"] = filename
    return sheet


def extract_lines(filename: str, content: bytes) -> list[str]:
    """The file as text lines; table cells are joined with " | "."""
    name = filename.lower()
    if name.endswith((".txt", ".text")):
        return content.decode("utf-8", "replace").splitlines()
    if name.endswith(".csv"):
        return [" | ".join(row) for row in csv.reader(io.StringIO(content.decode("utf-8", "replace")))]
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        return [" | ".join(_cell(c) for c in row) for sheet in book.worksheets
                for row in sheet.iter_rows(values_only=True) if any(c is not None for c in row)]
    if name.endswith(".pdf"):
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return [line for page in pdf.pages for line in (page.extract_text() or "").splitlines()]
    if name.endswith(".docx"):
        import docx
        document = docx.Document(io.BytesIO(content))
        lines = [p.text for p in document.paragraphs]
        for table in document.tables:
            lines += [" | ".join(cell.text for cell in row.cells) for row in table.rows]
        return lines
    if name.endswith((".jpg", ".jpeg", ".png")):
        raise TariffError(f"{filename} is an image: a person has to enter it")
    raise TariffError(f"{filename}: unknown tariff file type")


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def _date(text: str) -> str | None:
    text = text.strip(" |'")
    if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", text):
        return f"{m[1]}-{m[2]}-{m[3]}"
    if m := re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text):
        return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    if m := re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text):
        if (month := MONTHS.get(m[2].lower())) is not None:
            return f"{m[3]}-{month:02d}-{int(m[1]):02d}"
    return None


def _breaks(text: str) -> list[float]:
    found = []
    for sign, n, from_kg, kg_plus in BREAK.findall(text):
        if n:
            found.append(0.0 if sign == "-" else float(n))
        else:
            found.append(float(from_kg or kg_plus))
    return found


def _lane(text: str, origin: str | None) -> tuple[str | None, str]:
    """('CGN-SYD', rest of the line without the lane) or (None, text)."""
    for pattern in (LANE_TO, LANE_ARROW, LANE_DASH):
        m = pattern.search(text)
        if m and m[1] in ORIGINS:
            return f"{m[1]}-{m[2]}", text[:m.start()] + " " + text[m.end():]
    if origin:  # a block per origin: the first cell is the destination ("LOS" or "Lagos (LOS)")
        first, _, rest = text.partition("|")
        if m := re.fullmatch(r"\s*(?:[^()|]*\()?([A-Z]{3})\)?\s*", first):
            return f"{origin}-{m[1]}", rest
    return None, text


def _parse(lines: list[str]) -> dict:
    sheet = {"airline": None, "currency": "EUR", "breaks_kg": None, "valid_from": None, "valid_to": None,
             "cbm_kg": 167, "lanes": []}
    lanes: dict[str, dict] = {}
    surcharges: dict[str, tuple[float, float]] = {}
    inline_surcharges, origin, block = False, None, None

    for raw in lines:
        text = raw.replace(" ", " ").strip()
        if not text.strip(" |"):
            continue
        if sheet["airline"] is None and "tariff" in text.lower() and "|" in text:
            sheet["airline"] = text.split("|")[0].strip(" '")
            continue
        if m := re.match(r"Currency\W+([A-Z]{3})", text):
            sheet["currency"] = m[1]
            continue
        if m := re.match(r"Valid\s+(from|to)\b(.*)", text, re.I):
            sheet["valid_from" if m[1].lower() == "from" else "valid_to"] = _date(m[2])
            continue
        if m := re.search(r"1\s*cbm\s*=\s*(\d+)\s*kg", text):
            sheet["cbm_kg"] = int(m[1])
            continue
        if m := re.match(r"Origin:\s*(.*)", text):
            codes = re.findall(r"\b([A-Z]{3})\b", m[1])
            origin = next((c for c in codes if c in ORIGINS), None)
            block = None
            continue

        lane, rest = _lane(text, origin)
        if lane and (s := SURCHARGE.search(rest)):
            surcharges[lane] = (_num(s[1]), _num(s[2]))
            continue
        if lane:
            numbers = [_num(n) for n in NUMBER.findall(rest)]
            if numbers:  # one row per lane: transit, minimum, a rate per break (+ fuel, security)
                width = len(sheet["breaks_kg"] or [])
                want = 2 + width + (2 if inline_surcharges else 0)
                if not width or len(numbers) != want:
                    raise TariffError(f"{lane}: {len(numbers)} numbers, expected {want} ({text[:80]})")
                entry = {"lane": lane, "transit_days": int(numbers[0]), "minimum": numbers[1],
                         "rates": numbers[2:2 + width]}
                if inline_surcharges:
                    entry["fuel"], entry["security"] = numbers[-2], numbers[-1]
                lanes[lane] = entry
                block = None
            else:  # a vertical block starts: Transit / Minimum / from N kg R / Fuel / Security on the next lines
                lanes[lane] = {"lane": lane, "rates": [], "breaks": []}
                block = lanes[lane]
            continue

        if block is not None and (m := re.match(r"(Transit|Minimum|Fuel|Security)\b\D*(\d+(?:[.,]\d+)?)", text, re.I)):
            key = {"transit": "transit_days", "minimum": "minimum", "fuel": "fuel", "security": "security"}[m[1].lower()]
            block[key] = int(_num(m[2])) if key == "transit_days" else _num(m[2])
            continue
        if block is not None and (m := re.match(r"from\s+(\d+)\s*kg\s+(\d+(?:[.,]\d+)?)", text, re.I)):
            block["breaks"].append(float(m[1]))
            block["rates"].append(_num(m[2]))
            continue

        found = _breaks(text)
        if len(found) >= 4 and found[0] == 0:
            sheet["breaks_kg"] = found
            inline_surcharges = bool(re.search(r"\bfuel\b", text, re.I) and re.search(r"\bsecurity\b", text, re.I))

    for entry in lanes.values():
        if "breaks" in entry:
            sheet["breaks_kg"] = sheet["breaks_kg"] or entry["breaks"]
            if entry.pop("breaks") != sheet["breaks_kg"]:
                raise TariffError(f"{entry['lane']}: weight breaks differ from the rest of the sheet")
        if entry["lane"] in surcharges:
            entry["fuel"], entry["security"] = surcharges[entry["lane"]]
        missing = [k for k in ("transit_days", "minimum", "fuel", "security") if k not in entry]
        if missing or len(entry["rates"]) != len(sheet["breaks_kg"] or []):
            raise TariffError(f"{entry['lane']}: incomplete ({', '.join(missing) or 'rates'})")
    if not sheet["airline"] or not lanes or not sheet["valid_from"] or not sheet["valid_to"]:
        raise TariffError("not a tariff: airline, validity or lanes not found")
    sheet["breaks_kg"] = [int(b) if float(b).is_integer() else b for b in sheet["breaks_kg"]]
    sheet["lanes"] = list(lanes.values())
    return sheet
