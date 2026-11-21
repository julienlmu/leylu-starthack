"""Tariff ingestion: an airline's tariff file (xlsx, pdf, docx, txt, csv) → a sheet in the shape of data/tariffs.json.

No LLM: one rule-based parser for the layouts seen in the start kit (rows per lane, a block per origin, or a vertical
block per lane; surcharges inline or as "LANE: fuel X per kg, security Y per kg" lines). Images (Danube's photos)
can't be read here: they come back as an error so a person enters them.
"""

import calendar
import csv
import io
import os
import re
from datetime import date, datetime

import doctext

ORIGINS = {"CGN", "DUS", "FRA", "HAM", "MUC", "STR"}  # every pickup zone maps to one of these (data/pickup_zones.csv)
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
# TARIFF_DATES: validity written other ways too: "Validity: 01.12.2026 - 31.12.2026", "Gültig vom 01.12.2026 bis
# 31.12.2026", "December 1, 2026", "1. Dezember 2026", and no validity line at all when the file name says 2026-12
# (the monthly file). `TARIFF_DATES=off` reads only the start-kit wordings again.
TARIFF_DATES = os.environ.get("TARIFF_DATES", "on").lower() != "off"
MONTH_NAMES = {**MONTHS, **{m[:3]: i for m, i in MONTHS.items()}, "sept": 9,
               "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "maerz": 3, "mär": 3, "mrz": 3, "mai": 5, "juni": 6,
               "juli": 7, "oktober": 10, "okt": 10, "dezember": 12, "dez": 12}
VALIDITY = re.compile(r"(?:validity(?:\s+period)?|valid(?:ity)?\s+(?:period|dates?)|gültig(?:keit)?|gueltig(?:keit)?|"
                      r"gültigkeitszeitraum|period)\b(.*)", re.I)
FILE_MONTH = re.compile(r"(20\d{2})[-_.](0[1-9]|1[0-2])(?!\d)")
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
    sheet = _parse(lines, filename)
    sheet["file"] = filename
    return sheet


def extract_lines(filename: str, content: bytes, depth: int = 0, passwords=()) -> list[str]:
    """The file as text lines (see _extract_lines). A file whose extension lies ("a PDF named .xlsx", HACKATHON_GAPS)
    is read again by its first bytes when the named type fails."""
    try:
        return _extract_lines(filename, content, depth, passwords)
    except Exception:
        kind = doctext._sniff(content)
        named = filename.lower().rsplit(".", 1)[-1]
        if not kind or kind == named or depth > 2:
            raise
        return _extract_lines(f"{filename}.{kind}", content, depth + 1, passwords)


def _extract_lines(filename: str, content: bytes, depth: int = 0, passwords=()) -> list[str]:
    """The file as text lines; table cells are joined with " | ". Other document types (old Office, OpenDocument,
    pptx, rtf, html, eml, zip, …): doctext.py. Hidden parts (Word headers / text boxes / comments, PDF form fields /
    notes / embedded files, Excel comments / uncached formulas) come after the page text. `passwords`: from the mail
    body, tried on an encrypted PDF or zip."""
    name = filename.lower()
    read = lambda n, data, d: extract_lines(n, data, d, passwords)  # noqa: E731 (a file inside a zip / PDF / mail)
    if "." not in name.rsplit("/", 1)[-1] and (kind := doctext._sniff(content)) in ("pdf", "docx", "xlsx"):
        name = f"{name}.{kind}"  # an attachment without an extension, recognised by its first bytes
    if name.endswith((".txt", ".text")):
        return content.decode("utf-8", "replace").splitlines()
    if name.endswith(".csv"):
        return [" | ".join(row) for row in csv.reader(io.StringIO(content.decode("utf-8", "replace")))]
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        book = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        return [" | ".join(_cell(c) for c in row) for sheet in book.worksheets
                for row in sheet.iter_rows(values_only=True) if any(c is not None for c in row)] + \
            doctext.excel_extra(content)
    if name.endswith(".pdf"):
        import pdfplumber
        from pdfminer.pdfdocument import PDFPasswordIncorrect
        from pdfplumber.utils.exceptions import PdfminerException
        for password in ("", *passwords):  # only the mail's own hints, never a guess
            try:
                pdf = pdfplumber.open(io.BytesIO(content), password=password)
                break
            except PdfminerException as error:
                if not (error.args and isinstance(error.args[0], PDFPasswordIncorrect)):
                    raise
        else:
            raise TariffError(f"{filename} is password-protected: no password from the mail opens it")
        with pdf:
            return [line for page in pdf.pages for line in (page.extract_text() or "").splitlines()] + \
                doctext.pdf_extra(pdf, read, depth)
    if name.endswith(".docx"):
        import docx
        document = docx.Document(io.BytesIO(content))
        lines = [p.text for p in document.paragraphs]
        for table in document.tables:
            lines += [" | ".join(cell.text for cell in row.cells) for row in table.rows]
        return lines + doctext.word_extra(content, lines)
    if name.endswith((".jpg", ".jpeg", ".png")):
        raise TariffError(f"{filename} is an image: a person has to enter it")
    found = doctext.lines(name, content, read=read, depth=depth, passwords=passwords)
    if found is None:
        raise TariffError(f"{filename}: unknown tariff file type")
    return found


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def _valid(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def _date(text: str) -> str | None:
    """ISO date from 2026-11-01, 01.11.2026, 01/11/2026 (11/30/2026 read as month/day), 1 November 2026."""
    text = text.strip(" |'")
    if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", text):
        return _valid(int(m[1]), int(m[2]), int(m[3]))
    if m := re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text):
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        return _valid(y, b, a) or _valid(y, a, b)
    if m := re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text):
        if (month := MONTHS.get(m[2].lower())) is not None:
            return _valid(int(m[3]), month, int(m[1]))
    if TARIFF_DATES and (found := _dates(text)):
        return found[0]
    return None


WORD_DATES = (  # (pattern, (year, month name, day) groups)
    (re.compile(r"(\d{1,2})\.?\s+([A-Za-zÄÖÜäöü]+)\.?\s+(\d{4})"), (3, 2, 1)),     # 1 December 2026, 1. Dezember 2026
    (re.compile(r"([A-Za-zÄÖÜäöü]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})"), (3, 1, 2)),  # December 1, 2026
)


def _dates(text: str) -> list[str]:
    """Every date in the text, in order (TARIFF_DATES): numeric and written months, English and German."""
    found = []
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", text):
        found.append((m.start(), _valid(int(m[1]), int(m[2]), int(m[3]))))
    for m in re.finditer(r"(?<![\d.])(\d{1,2})[./](\d{1,2})[./](\d{4})", text):
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        found.append((m.start(), _valid(y, b, a) or _valid(y, a, b)))
    for pattern, (y, mo, d) in WORD_DATES:
        for m in pattern.finditer(text):
            if (month := MONTH_NAMES.get(m[mo].lower())) is not None:
                found.append((m.start(), _valid(int(m[y]), month, int(m[d]))))
    return [iso for _, iso in sorted(found) if iso]


def _validity(sheet: dict, rest: str) -> bool:
    """"Validity: 01.12.2026 - 31.12.2026", "Gültig vom … bis …", "Gültig ab …" / "bis …". True when it set a date."""
    found = _dates(rest)
    if len(found) >= 2:
        sheet["valid_from"], sheet["valid_to"] = found[0], found[1]
    elif found and re.match(r"\W*(?:bis|until|till|to|through|thru)\b", rest, re.I):
        sheet["valid_to"] = found[0]
    elif found:
        sheet["valid_from"] = found[0]
    return bool(found)


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


def _parse(lines: list[str], filename: str = "") -> dict:
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
        if TARIFF_DATES and (m := VALIDITY.match(text)) and _validity(sheet, m[1]):
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
                entry = {"lane": lane, "transit_days": numbers[0] if numbers[0] % 1 else int(numbers[0]), "minimum": numbers[1],
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
    if TARIFF_DATES and (m := FILE_MONTH.search(filename)) and not (sheet["valid_from"] and sheet["valid_to"]):
        y, mo = int(m[1]), int(m[2])  # no validity in the file: the monthly file name says which month
        sheet["valid_from"] = sheet["valid_from"] or date(y, mo, 1).isoformat()
        sheet["valid_to"] = sheet["valid_to"] or date(y, mo, calendar.monthrange(y, mo)[1]).isoformat()
    if not sheet["airline"] or not lanes or not sheet["valid_from"] or not sheet["valid_to"]:
        raise TariffError("not a tariff: airline, validity or lanes not found")
    if sheet["valid_from"] > sheet["valid_to"]:
        raise TariffError(f"validity {sheet['valid_from']} to {sheet['valid_to']} is backwards")
    sheet["breaks_kg"] = [int(b) if float(b).is_integer() else b for b in sheet["breaks_kg"]]
    sheet["lanes"] = list(lanes.values())
    return sheet
