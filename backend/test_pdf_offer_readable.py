"""The agent's quote PDF (agent/pdf_offer.py) opens in a real PDF reader with the same single amount."""
import io
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import pdf_offer  # noqa: E402


def test_the_quote_pdf_reads_back_with_one_amount_and_umlauts():
    text = ("Hallo Anna,\n\nLumen Air Cargo kann Ihre 3 Packstücke (640 kg) von MUC nach ORD fliegen, für "
            "EUR 2,345.67 all-in.\n\nDanke und Grüße\nLena")
    with pdfplumber.open(io.BytesIO(pdf_offer.build(text))) as pdf:
        out = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert re.findall(r"\d[\d,.]*\.\d{2}", out) == ["2,345.67"] and "Packstücke" in out and "Grüße" in out


def test_a_long_quote_breaks_into_pages():
    with pdfplumber.open(io.BytesIO(pdf_offer.build("\n".join(f"line {i}" for i in range(200))))) as pdf:
        assert len(pdf.pages) == 4
