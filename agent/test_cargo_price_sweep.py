"""Cargo-price sweep: phrasing variants (EN/DE, some FR/IT/ES) of the traps 5U already sprang or is likely to spring next.

Live rejects so far: R1 too_low (door-to-port without the trucker), R10/R11 dg_docs_missing (DG only in the packing
list / SLI), R15 too_high. Each case asserts what a careful forwarder does before the quote leaves:
- DG in any spelling → the quote asks for the Shipper's Declaration for Dangerous Goods and the MSDS; "non-DG" /
  "kein Gefahrgut" / "Gefahrgut: nein" → it doesn't;
- temperature, perishables, valuables, oversize → one sentence (no digits), live animals / human remains → a person;
  false friends ("PET film", "frozen price", "golden retriever toy") → nothing;
- a total that a missing or double-counted part explains → held for a person (auto-send at 240 s), a clean one is not.
Every quote states exactly one amount. Rules only: no LLM call anywhere here (LLM cost is 40 % of the score).

Kill switches (default on, `=off` restores the old behaviour exactly): CARGO_WORDS_V2, OVERSIZE_TEXT, PRICE_SANITY_V2
(gate.py), FALLBACK_GATE, DG_FOLLOWUP (rfq_agent.py). xfail(strict=True) = a gap rules can't close safely (see reason).
Run: cd agent && NEXT_TRAPS_PORT=8831 uv run pytest -q test_cargo_price_sweep.py -rxX
"""

import base64
import io
import zipfile
from types import SimpleNamespace

import pytest

import amendments
import dg as dg_mod
import extract as extract_mod
import gate
import rfq_agent
import test_traps
from bids import parse_bid
from dg import dg_info
from extract import to_rfq
from inbox import FixtureMailbox
from templates import quote_text
from test_rfq_agent import FakeApi
from test_traps import BASE_RAW, CASES, GateApi

XF = lambda reason: pytest.mark.xfail(strict=True, reason=reason)  # noqa: E731
DG_PAPERS = ("Shipper's Declaration for Dangerous Goods", "MSDS")


def opt(carrier, total, days, source="sheet", pickup=None, breakdown=(), chargeable=715.0):
    return {"source": source, "leg": "air", "carrier": carrier, "rate_id": None, "currency": "EUR", "total": total,
            "transit_days": days, "valid_until": "2026-11-30", "chargeable_weight_kg": chargeable,
            "breakdown": list(breakdown), "pickup": pickup}


THREE = [opt("Kestrel Airways", 2400.0, 5), opt("Helix Air Freight", 2900.0, 2), opt("Vega Skyfreight", 3100.0, 3)]


def priced(options=None, chosen=0, warnings=()):
    options = THREE if options is None else options
    return {"options": options, "chosen": options[chosen], "why": "test", "warnings": list(warnings)}


def request(**raw):
    rfq, _ = to_rfq({**BASE_RAW, **raw})
    rfq["contact_name"] = None
    return rfq


def check(body, texts=(), files=(), raw=None, result=None, subject="Air freight quote"):
    """The checks between pricing and sending, as rfq_agent runs them: dg.py's rule, the gate, the written mail."""
    rfq = request(**(raw or {}))
    if info := dg_info(body, *texts):
        rfq["dangerous_goods"], rfq["dg_declared"] = True, info
    result = result or priced()
    mail = {"subject": subject, "body": body, "attachments": [{"id": i, "filename": f} for i, f in enumerate(files)]}
    verdict = gate.review(rfq, result, mail, list(texts))
    text, more = gate.finish(quote_text(rfq, verdict["chosen"], body), verdict, rfq)
    findings = verdict["findings"] + more
    assert gate.MONEY.findall(text) == [f"{verdict['chosen']['total']:,.2f}"], text  # one amount, always
    return SimpleNamespace(rfq=rfq, text=text, codes={f["code"] for f in findings}, findings=findings,
                           hold=verdict["hold"] or any(f["level"] == "hold" for f in more), chosen=verdict["chosen"])


def asks_dg_papers(c) -> bool:
    return bool(c.rfq.get("dangerous_goods")) and all(p in c.text for p in DG_PAPERS)


# ---- 1. dangerous goods ----------------------------------------------------------------------------------------------

DG_WRITTEN = [
    # UN numbers in every spelling
    ("4 cartons of power tool batteries, UN 3480, 120 kg.", "en"),
    ("Laptops packed with their batteries, UN-3481, 300 kg.", "en"),
    ("Data loggers with lithium metal cells contained in equipment (UN3091), 80 kg.", "en"),
    ("Goods: industrial coating, UN No. 1263, 40 kg.", "en"),
    ("Goods: refrigerant samples, UN number 1078, 20 kg.", "en"),
    ("Reinigungskonzentrat, UN-Nr. 1993, 300 kg.", "de"),
    ("Marchandise : concentré de nettoyage, numéro ONU 1993.", "fr"),
    ("Item 4: un3480 cells, 2 cartons.", "en"),
    ("Goods: coating samples, UN#1263, 40 kg.", "en"),
    # class / regulation only
    ("Goods: Class 9 miscellaneous, 2 pallets.", "en"),
    ("Hazard: Class 3, 4 drums of coating.", "en"),
    ("DG class 8, 2 drums.", "en"),
    ("Klasse 3, 6 Kanister Reinigungsmittel.", "de"),
    ("Class 2.1, 10 cartons.", "en"),
    ("The drums travel under the IMDG Code to the port afterwards.", "en"),
    ("Shipped under IATA DGR, 2 boxes, PG II.", "en"),
    ("ADR-Klasse 8 für den Vorlauf, 2 Fässer.", "de"),
    ("Contents packed in limited quantities (LQ), 3 cartons.", "en"),
    # lithium batteries in / with equipment, PI 965-970
    ("Cordless drills with Li-ion batteries installed (PI 967 Section II), 200 kg.", "en"),
    ("Lithium-ion cells, packing instruction 965, 4 cartons.", "en"),
    ("Spare batteries packed with the scanners, PI 966.", "en"),
    ("Watches with button cells, PI 970.", "en"),
    ("150 cartons of power banks.", "en"),
    ("12 e-bikes on 3 pallets.", "en"),
    ("Akkuschrauber mit Lithium-Ionen-Akkus, 20 Kartons.", "de"),
    ("Lithiumbatterien, 20 Kartons, 340 kg.", "de"),
    ("Ersatzakkus (Li-Ion) für E-Bikes, 2 Paletten.", "de"),
    ("Outillage avec batteries au lithium, 3 palettes.", "fr"),
    ("Herramientas con baterías de litio, 3 palés.", "es"),
    ("Utensili con batterie al litio, 3 pallet.", "it"),
    # dry ice
    ("6 boxes of clinical samples packed in dry ice.", "en"),
    ("Proben in Trockeneis, 4 Boxen.", "de"),
    ("Échantillons sous glace carbonique, 4 boîtes.", "fr"),
    ("Muestras con hielo seco, 4 cajas.", "es"),
    ("Campioni in ghiaccio secco, 4 scatole.", "it"),
    # aerosols, perfumes, flammable liquids, paints
    ("Aerosol deodorants, 12 cartons.", "en"),
    ("Lack in Spraydosen, 8 Kartons.", "de"),
    ("Eau de parfum samples, 3 cartons.", "en"),
    ("Parfüm, 3 Kartons, 90 kg.", "de"),
    ("Parfums et eaux de toilette, 5 cartons.", "fr"),
    ("Profumi, 5 cartoni.", "it"),
    ("Nail polish, 600 bottles.", "en"),
    ("Nagellack, 600 Flaschen.", "de"),
    ("Isopropanol for cleaning, 4 canisters.", "en"),
    ("Hand sanitizer, 2 pallets.", "en"),
    ("Highly flammable liquid, 2 drums.", "en"),
    ("Leicht entzündliche Flüssigkeit, 2 Fässer.", "de"),
    ("Liquide inflammable, 2 fûts.", "fr"),
    ("Líquido inflamable, 2 bidones.", "es"),
    ("Liquido infiammabile, 2 fusti.", "it"),
    ("Industrial paints and varnishes, 1 pallet.", "en"),
    # magnets and the rest
    ("Neodymium magnets, 2 cartons.", "en"),
    ("Magnetized material for speakers, 1 box.", "en"),
    ("Neodym-Magnete, 2 Kartons.", "de"),
    ("Airbag modules for the assembly line, 4 cartons.", "en"),
    ("Fire extinguishers, 30 pieces.", "en"),
    ("Car batteries (lead-acid), 1 pallet.", "en"),
    # DG named as such
    ("This is a dangerous goods shipment, 3 crates.", "en"),
    ("The crates contain hazardous materials.", "en"),
    ("Hazmat, 3 drums.", "en"),
    ("DG cargo, 2 pallets.", "en"),
    ("Die Sendung ist Gefahrgut.", "de"),
    ("Es handelt sich um Gefahrgüter der Klasse 8.", "de"),
    ("Il s'agit de marchandises dangereuses.", "fr"),
    ("Son mercancías peligrosas.", "es"),
    ("Sono merci pericolose.", "it"),
    # a negation that ends before the DG word
    ("Not stackable, dry ice inside.", "en"),
    ("No dangerous goods except the dry ice in box 4.", "en"),
    ("Kein Gefahrgut außer dem Trockeneis in Box 4.", "de"),
    # a yes answer
    ("DG: yes, see the MSDS attached.", "en"),
    ("Hazardous: yes", "en"),
]


@pytest.mark.parametrize("body,language", DG_WRITTEN, ids=[b[:40] for b, _ in DG_WRITTEN])
def test_dangerous_goods_in_any_spelling_get_the_dg_papers_asked(body, language):
    c = check(f"Hi,\n\nplease quote the cheapest option. {body}\n\nThanks", raw={"language": language})
    assert asks_dg_papers(c), (c.findings, c.text)
    assert not c.hold  # a sentence handles DG: no person needed


NOT_DG = [
    "General cargo, non-DG, machine parts.",
    "No dangerous goods, no lithium batteries, no aerosols.",
    "Not DG. Dangerous goods: not restricted.",
    "Dangerous goods: no",
    "Dangerous goods: N/A",
    "Contains no aerosols, perfumes or lithium batteries.",
    "Kein Gefahrgut, Maschinenteile.",
    "Gefahrgut: nein",
    "Gefahrgut: keins",
    "Es handelt sich nicht um Gefahrgut.",
    "Keine Gefahrgüter, keine Lithiumbatterien.",
    "Die Ware ist gefahrgutfrei.",
    "Lithiumbatterien sind nicht enthalten.",
    "Pas de matières dangereuses.",
    "Il ne s'agit pas de marchandises dangereuses.",
    "No son mercancías peligrosas.",
    "Envío sin mercancías peligrosas.",
    "Non sono merci pericolose.",
    "Tehlikeli madde değildir.",
    # false friends
    "Paint brushes and paint rollers, 4 pallets.",
    "Paint spray guns, 2 crates.",
    "The crates are lighter than last time.",
    "Due to a lack of space we split the order.",
    "Pickup in Cologne, please include the fuel surcharge in the all-in price.",
    "ISO class 7 cleanroom garments, 3 cartons.",
    "Class 2 medical devices (infusion pumps), 3 crates.",
    "Laser class 1 barcode scanners, 2 cartons.",
    "E-bike helmets, 40 cartons.",
    "Fragrance-free soap, 2 pallets.",
    "Parfümfreie Seife, 2 Paletten.",
    "Schwer entflammbare Vorhänge, 2 Paletten.",
    "Lithium grease for bearings, 1 pallet.",
    "Flame retardant fabric rolls.",
    "Un total de 1500 kg, mercancía general.",
]


@pytest.mark.parametrize("body", NOT_DG, ids=[b[:40] for b in NOT_DG])
def test_non_dg_and_false_friends_get_no_dg_paragraph(body):
    c = check(f"Hi,\n\nplease quote the cheapest option. {body}\n\nThanks")
    assert not c.rfq.get("dangerous_goods") and "MSDS" not in c.text, c.findings
    assert "dangerous_goods" not in c.codes


@pytest.mark.parametrize("texts,files", [
    (["Packing list\nItem | Goods | Gross kg\n1 | Cordless drills, Li-ion batteries in equipment, PI 967 | 200"], []),
    (["Shipper's Letter of Instruction\nGoods: maintenance kit incl. one spray can"], []),
    (["SLI\nGoods description: samples, refrigerated with Trockeneis"], []),
    ([], ["Lithium_Battery_Declaration_PI966.pdf"]),
    ([], ["UN38.3_test_summary.pdf"]),
    ([], ["Trockeneis_Erklaerung.pdf"]),
    ([], ["DG_declaration.pdf"]),
], ids=["pl-text-pi967", "sli-spray-can", "sli-trockeneis", "name-lithium", "name-un38.3", "name-trockeneis",
        "name-dg-declaration"])
def test_dg_only_in_an_attachment_text_or_name(texts, files):
    c = check("Hi,\n\n3 pieces of spare parts, general cargo, non-dangerous. Documents attached.\n\nThanks",
              texts=texts, files=files)
    assert asks_dg_papers(c), c.findings


def test_a_non_dg_attachment_name_is_no_dg():
    c = check("Hi,\n\n3 pieces of spare parts.\n\nThanks", files=["non_dangerous_goods_declaration.pdf", "PL_4471.xlsx"])
    assert not c.rfq.get("dangerous_goods")


# packing lists as the backend reads them (xlsx/docx cells joined by " | "): a column or heading named "Dangerous goods"
# claims nothing when the list answers no; any other answer, or the word in a value cell, is DG
PLAIN = "Hi,\n\n3 pieces, cheapest please. Packing list attached.\n\nThanks"


@pytest.mark.parametrize("table", [
    "Item | Pieces | Dangerous goods | Gross weight\n1 | 3 | Yes | 715",
    "Item | Description | Pieces\n1 | Lithium batteries | 4",
    "Goods description: | Dry ice",
    "Dry ice | 5 kg",
    "Dangerous goods | Yes",
    "Dangerous goods\nLithium batteries in equipment",
    "Lithium batteries\n4 cartons",
], ids=["column-yes", "value-cell", "key-value", "row-with-amount", "row-yes", "heading-answered", "heading-amount"])
def test_dg_in_a_packing_list_table(table):
    assert asks_dg_papers(check(PLAIN, texts=[table]))


@pytest.mark.parametrize("table", [
    "Item | Pieces | Dangerous goods | Gross weight\n1 | 3 | No | 715",
    "| Item | Dangerous goods |\n|---|---|\n| 1 | No |",
    "Item | Dangerous goods | Weight\n1 |  | 715\n2 | - | 300",
    "Goods description: | spare parts\nDangerous goods: | No",
    "Dangerous goods | None",
    "Gefahrgut: | nein",
    "Dangerous goods\nNone",
    "Dry ice | No",
    "Item | Dangerous goods (Y/N) | Weight\n1 | N/A | 715",
], ids=["column-no", "markdown", "blank-and-dash", "key-value-no", "row-none", "german", "heading-none", "dry-ice-no",
        "y-n-column"])
def test_a_dg_column_answered_no_is_no_dg(table):
    c = check(PLAIN, texts=[table])
    assert not c.rfq.get("dangerous_goods") and "MSDS" not in c.text, c.findings


@pytest.mark.parametrize("table,code", [
    ("Item | Perishable | Weight\n1 | Yes | 715", "perishable"),
    ("Item | Perishable | Weight\n1 | No | 715", None),
    ("Temperature controlled | No", None),
], ids=["perishable-yes", "perishable-no", "temperature-no"])
def test_a_special_cargo_column_reads_its_answer(table, code):
    codes = check(PLAIN, texts=[table]).codes & {k for k, *_ in gate.SPECIAL}
    assert codes == ({code} if code else set())


@XF("a product with a built-in lithium battery named only by the product (laptops, Akku-Bohrschrauber) isn't flagged: "
    "'electronic control units' is 5U's everyday general cargo and PI 967 Section II needs no DGD, so asking for the "
    "Shipper's Declaration on every electronics RFQ would be wrong more often than right")
@pytest.mark.parametrize("body", ["20 cartons of laptops, 400 kg.", "Akku-Bohrschrauber, 2 Paletten."])
def test_lithium_only_implied_by_the_product_name(body):
    assert asks_dg_papers(check(f"Hi,\n\n{body}\n\nThanks"))


def test_cargo_words_v2_off_is_the_old_reading(monkeypatch):
    monkeypatch.setattr(gate, "CARGO_WORDS_V2", False)
    assert not check("Goods: industrial coating, UN No. 1263, 40 kg.").rfq.get("dangerous_goods")  # old: missed
    assert check("Gefahrgut: nein. Maschinenteile.").rfq.get("dangerous_goods")  # old: false alarm
    assert "temperature" in check("Our prices are frozen until December.").codes  # old: false alarm
    assert asks_dg_papers(check("6 boxes of samples packed in dry ice."))  # old rules still work


# ---- 1b. DG through the whole pipeline: attachment text, a follow-up mail, a late trucker --------------------------

class TextApi(GateApi):
    """GateApi whose backend reads attachment text (PDF and friends) like /api/attachments/text."""

    def __init__(self, price_result, text=""):
        super().__init__(price_result)
        self.text = text

    def attachment_text(self, filename, content_base64):
        return self.text


def _pipeline(monkeypatch, tmp_path, body, api, raw=None, attachments=(), later=(), box=None):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: ({**BASE_RAW, **(raw or {})}, 0.0001))
    monkeypatch.setattr(rfq_agent, "GATE_AUTO_SEND_SECONDS", 0.0)
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0.0)
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: None)
    box = box or FixtureMailbox(tmp_path)
    mail = {"id": "m1", "thread_id": f"t-sweep-{len(body)}-{id(api)}", "from": "buyer@customer.example",
            "subject": "Air freight quote", "body": body, "attachments": list(attachments)}
    for i, m in enumerate(later):
        amendments.add(mail["thread_id"], {"id": f"m{i + 2}", "thread_id": mail["thread_id"], "subject": "Re: quote",
                                           "from": mail["from"], "attachments": [], **m})
    rfq_agent.handle_rfq(mail, box, api)
    return [s for s in box.sent if s["thread_id"] == mail["thread_id"]]


def _file(name, data: bytes):
    return {"id": 9, "filename": name, "content_base64": base64.b64encode(data).decode()}


def _xlsx(*cells):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", "<sst>" + "".join(f"<si><t>{c}</t></si>" for c in cells) + "</sst>")
    return buf.getvalue()


NON_DG_BODY = "Hi,\n\n3 pieces of spare parts, 715 kg, 2.65 cbm, FRA to GRU, ready 2026-11-25. General cargo.\n\nTom"


def test_dg_only_in_a_pdf_sli_that_the_backend_reads(monkeypatch, tmp_path):
    api = TextApi(priced(), "Shipper's Letter of Instruction\nGoods: cordless drills, Li-ion batteries in equipment")
    [quote] = _pipeline(monkeypatch, tmp_path, NON_DG_BODY, api, attachments=[_file("SLI_771.pdf", b"%PDF-1.4")])
    assert all(p in quote["body"] for p in DG_PAPERS)


def test_dg_only_in_a_follow_up_mail_before_our_quote(monkeypatch, tmp_path):
    later = [{"body": "Sorry, I forgot to mention: the cartons are packed with dry ice.\n\n> earlier mail"}]
    [quote] = _pipeline(monkeypatch, tmp_path, NON_DG_BODY, GateApi(priced()), later=later)
    assert all(p in quote["body"] for p in DG_PAPERS)


def test_a_packing_list_sent_in_a_follow_up_mail(monkeypatch, tmp_path):
    pl = _file("PL_8812.xlsx", _xlsx("Dangerous goods:", "UN1133, Class 3, Adhesives"))
    later = [{"body": "Please find the packing list attached.", "attachments": [pl]}]
    [quote] = _pipeline(monkeypatch, tmp_path, NON_DG_BODY, GateApi(priced()), later=later)
    assert all(p in quote["body"] for p in DG_PAPERS)


def test_dg_followup_off_reads_the_follow_up_for_figures_only(monkeypatch, tmp_path):
    monkeypatch.setattr(rfq_agent, "DG_FOLLOWUP", False)
    later = [{"body": "Sorry, I forgot to mention: the cartons are packed with dry ice."}]
    [quote] = _pipeline(monkeypatch, tmp_path, NON_DG_BODY, GateApi(priced()), later=later)
    assert "MSDS" not in quote["body"]  # the old behaviour (the re-read's LLM flag was the only DG check)


def test_a_follow_up_saying_no_dg_adds_nothing(monkeypatch, tmp_path):
    later = [{"body": "To confirm: no dangerous goods, no lithium batteries."}]
    [quote] = _pipeline(monkeypatch, tmp_path, NON_DG_BODY, GateApi(priced()), later=later)
    assert "MSDS" not in quote["body"]


class CountingBox(FixtureMailbox):
    def __init__(self, path):
        super().__init__(path)
        self.downloads = []

    def attachment(self, mail, attachment):
        self.downloads.append(attachment["filename"])
        return super().attachment(mail, attachment)


def test_a_scanned_attachment_in_a_follow_up_counts_its_vision_cost_and_is_downloaded_once(monkeypatch, tmp_path):
    import scans  # Julien's review of #143: the vision call's cost must reach llm_cost_usd
    reads = []
    monkeypatch.setattr(scans, "IMAGE_READ", True)
    monkeypatch.setattr(scans, "read", lambda name, data, timeout=None: (reads.append(name) or "Packing list: 5 kg dry ice", 0.0123))
    api, box = TextApi(priced(), text=""), CountingBox(tmp_path)  # the backend finds no text layer in the scan
    later = [{"body": "Packing list attached.", "attachments": [_file("packing_list_scan.jpg", b"\xff\xd8\xff")]}]
    [quote] = _pipeline(monkeypatch, tmp_path, NON_DG_BODY, api, later=later, box=box)
    assert reads == ["packing_list_scan.jpg"] and box.downloads == ["packing_list_scan.jpg"]
    costs = [u["llm_cost_usd"] for u in api.updates if "llm_cost_usd" in u]
    assert costs[-1] == pytest.approx(0.0001 + 0.0001 + 0.0123)  # extraction, re-read, the scan
    assert all(p in quote["body"] for p in DG_PAPERS)  # the dry ice in the scan


AIR = opt("Kestrel Airways", 2400.0, 5)
DOOR = {**AIR, "total": 2519.01, "transit_days": 6,
        "pickup": {"carrier": "Huber Transporte", "rate_id": None, "total": 119.01, "transit_days": 1}}
DOOR_RAW = {"origin": "MUC", "pickup_address": "Industriestr. 12, 85748 Garching"}


def _no_trucker_api():
    """/api/price at the cut-off: door-to-port but no trucker bid → no all-in price; the fallback finds an earlier bid."""
    api = FakeApi({"options": [AIR], "chosen": None, "why": "door-to-port but no trucker bid: no all-in price"})
    api.fallback_result = {"options": [DOOR], "chosen": DOOR, "why": "earlier trucker bid for zone 85"}
    return api


def test_r1_no_trucker_bid_means_no_port_to_port_quote_but_a_fallback_with_the_pickup(monkeypatch, tmp_path):
    api = _no_trucker_api()
    [quote] = _pipeline(monkeypatch, tmp_path, NON_DG_BODY.replace("FRA to GRU", "pickup in 85748 Garching to GRU"),
                        api, raw=DOOR_RAW)
    assert "2,519.01" in quote["body"] and "2,400.00" not in quote["body"]
    assert api.fallback and api.data["quote_sent"]["option"]["pickup"]


def test_a_late_trucker_fallback_quote_still_asks_for_the_dg_papers(monkeypatch, tmp_path):
    body = "Hi,\n\nplease pick up at Industriestr. 12, 85748 Garching: 6 boxes of samples packed in dry ice.\n\nTom"
    [quote] = _pipeline(monkeypatch, tmp_path, body, _no_trucker_api(), raw=DOOR_RAW)
    assert all(p in quote["body"] for p in DG_PAPERS) and gate.MONEY.findall(quote["body"]) == ["2,519.01"]


def test_fallback_gate_off_sends_the_fallback_as_written(monkeypatch, tmp_path):
    monkeypatch.setattr(rfq_agent, "FALLBACK_GATE", False)
    body = "Hi,\n\nplease pick up at Industriestr. 12, 85748 Garching: 6 boxes of samples packed in dry ice.\n\nTom"
    [quote] = _pipeline(monkeypatch, tmp_path, body, _no_trucker_api(), raw=DOOR_RAW)
    assert "MSDS" not in quote["body"]  # the old gap: the fallback skipped the gate


def test_a_crashing_gate_never_costs_the_fallback_quote(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "review", lambda *a, **k: 1 / 0)
    [quote] = _pipeline(monkeypatch, tmp_path, NON_DG_BODY, _no_trucker_api(), raw=DOOR_RAW)
    assert gate.MONEY.findall(quote["body"]) == ["2,519.01"]


# ---- 2. special cargo ----------------------------------------------------------------------------------------------

SPECIAL_WRITTEN = [
    ("temperature", "Vaccines, keep at 2–8 °C.", "en"),
    ("temperature", "Please keep the goods at +15°C to +25°C.", "en"),
    ("temperature", "Store between 2°C and 8°C during transport.", "en"),
    ("temperature", "Pharma, +15 to +25, data logger inside.", "en"),
    ("temperature", "Cold chain shipment, 4 boxes.", "en"),
    ("temperature", "Temperature control needed throughout.", "en"),
    ("temperature", "Kühlware, 2 bis 8 °C.", "de"),
    ("temperature", "Die Sendung muss temperaturgeführt reisen.", "de"),
    ("temperature", "Tiefgekühlt bei -20 °C.", "de"),
    ("temperature", "Envoi sous température dirigée, chaîne du froid.", "fr"),
    ("temperature", "Mantener la cadena de frío.", "es"),
    ("temperature", "Rispettare la catena del freddo.", "it"),
    ("temperature", "Temperature range: 2 to 8.", "en"),
    ("temperature", "Pharma samples, 2-8C.", "en"),
    ("temperature", "Keep under 25 degrees.", "en"),
    ("perishable", "12 boxes of flowers.", "en"),
    ("perishable", "Fresh fish from Norway, 6 boxes.", "en"),
    ("perishable", "Fresh cut roses, 40 boxes.", "en"),
    ("perishable", "Schnittblumen, 40 Kartons.", "de"),
    ("perishable", "Frischer Lachs, 6 Boxen.", "de"),
    ("perishable", "Fleurs coupées, 40 cartons.", "fr"),
    ("perishable", "Flores cortadas, 40 cajas.", "es"),
    ("perishable", "Pesce fresco, 6 casse.", "it"),
    ("valuables", "Gold bars, 2 boxes.", "en"),
    ("valuables", "Jewellery samples, 1 box.", "en"),
    ("valuables", "Banknotes, 3 sealed boxes.", "en"),
    ("valuables", "High value electronics, 2 crates.", "en"),
    ("valuables", "Precious metal granules, 1 drum.", "en"),
    ("valuables", "Goldbarren, 2 Kisten.", "de"),
    ("valuables", "Schmuck, 1 Karton.", "de"),
    ("valuables", "Bijoux, 1 carton.", "fr"),
    ("valuables", "Joyas, 1 caja.", "es"),
    ("valuables", "Gioielli, 1 scatola.", "it"),
    ("non_stackable", "Top load only, 3 crates.", "en"),
    ("non_stackable", "Bitte nicht stapeln.", "de"),
]


@pytest.mark.parametrize("code,body,language", SPECIAL_WRITTEN, ids=[b[:40] for _, b, _ in SPECIAL_WRITTEN])
def test_special_cargo_gets_its_sentence(code, body, language):
    c = check(f"Hi,\n\nplease quote the cheapest option. {body}\n\nThanks", raw={"language": language})
    assert code in c.codes and not c.hold, c.findings
    sentence = next(en if language != "de" else de for k, _, _, en, de in gate.SPECIAL if k == code)
    assert sentence in c.text


HOLD_WRITTEN = [
    ("live_animals", "2 horses for a show jumping event."),
    ("live_animals", "Live lobsters, 10 boxes."),
    ("live_animals", "Day-old chicks, 40 boxes."),
    ("live_animals", "Lebende Tiere: zwei Hunde."),
    ("live_animals", "Animaux vivants, 2 chevaux."),
    ("live_animals", "Animales vivos, 2 caballos."),
    ("live_animals", "Animali vivi, 2 cavalli."),
    ("live_animals", "Tropical fish (live), 20 boxes."),
    ("live_animals", "Ornamental fish, 20 boxes."),
    ("human_remains", "Repatriation of mortal remains, 1 coffin."),
    ("human_remains", "An urn with the ashes of the deceased."),
    ("human_remains", "Überführung: ein Sarg."),
    ("human_remains", "Dépouille mortelle, 1 cercueil."),
    ("human_remains", "Restos mortales, 1 ataúd."),
]


@pytest.mark.parametrize("code,body", HOLD_WRITTEN, ids=[b[:40] for _, b in HOLD_WRITTEN])
def test_live_animals_and_human_remains_go_to_a_person(code, body):
    c = check(f"Hi,\n\nplease quote. {body}\n\nThanks")
    assert code in c.codes and c.hold, c.findings


FALSE_FRIENDS = [
    "12 rolls of PET film for packaging.",
    "Cool design lamps, 3 cartons.",
    "A golden retriever toy collection, 3 cartons.",
    "Our frozen price from last month should still apply.",
    "Prices are frozen until December, please confirm.",
    "Controllers rated for an operating temperature of -20 to +60 °C.",
    "No temperature control needed, ambient is fine.",
    "Non-perishable goods, 3 pallets.",
    "Pet food and dog toys, 2 pallets.",
    "Cat 6 cables, 4 cartons.",
    "Horse saddles, 1 pallet.",
    "Gold-plated connectors, 2 cartons.",
    "We place a high value on punctuality.",
    "Jewellery boxes (empty packaging), 3 pallets.",
    "Payment cash on delivery is not possible, please invoice.",
    "Diamond saw blades, 1 pallet.",
    "Decorative urns for the garden centre, 2 pallets.",
    "Salma Rossi, Logistics",
    "12 boxes of artificial flowers.",
    "Silk flowers for a trade fair, 3 cartons.",
    "Künstliche Blumen, 12 Kartons.",
    "Aquarium fish food, 20 boxes.",
    "USB-C chargers, 4 cartons.",
    "Type 2C controllers, 3 cartons.",
    "Garden hose length 15 m, 40 cartons.",
    "A 15 m long hose, 40 cartons.",
]


@pytest.mark.parametrize("body", FALSE_FRIENDS, ids=[b[:40] for b in FALSE_FRIENDS])
def test_false_friends_add_nothing(body):
    c = check(f"Hi,\n\nplease quote the cheapest option. {body}\n\nThanks")
    special = {k for k, *_ in gate.SPECIAL} | {"dangerous_goods", "oversize"}
    assert not (special & c.codes) and not c.hold, c.findings


# oversize: the extracted pieces (any unit) and, OVERSIZE_TEXT, sizes written in the mail or an attachment
@pytest.mark.parametrize("piece", [
    {"count": 1, "length": 120, "width": 80, "height": 175, "weight": 400},
    {"count": 1, "length": 320, "width": 120, "height": 100, "weight": 400},
    {"count": 1, "length": 200, "width": 120, "height": 100, "weight": 1600},
    {"count": 1, "length": 48, "width": 40, "height": 70, "weight": 400, "unit": "in"},
    {"count": 1, "length": 1200, "width": 800, "height": 1750, "weight": 400, "unit": "mm"},
], ids=["tall-cm", "long-cm", "heavy", "tall-inches", "tall-mm"])
def test_an_oversize_piece_flies_main_deck(piece):
    unit = piece.pop("unit", "cm")
    raw = {"dim_unit": unit, "volume": None,
           "pieces": [{**piece, "weight_is_total": True, "volume": None, "volume_is_total": True}]}
    c = check("Hi,\n\n1 crate, cheapest please.\n\nThanks", raw=raw)
    assert "oversize" in c.codes and "main deck" in c.text and not c.hold


@pytest.mark.parametrize("piece", [
    {"count": 1, "length": 120, "width": 80, "height": 160, "weight": 1500},
    {"count": 1, "length": 300, "width": 120, "height": 150, "weight": 900},
    {"count": 1, "length": 48, "width": 40, "height": 60, "weight": 400, "unit": "in"},
], ids=["at-the-limits", "300-long", "60-inches"])
def test_a_piece_at_the_limits_stays_lower_deck(piece):
    unit = piece.pop("unit", "cm")
    raw = {"dim_unit": unit, "volume": None,
           "pieces": [{**piece, "weight_is_total": True, "volume": None, "volume_is_total": True}]}
    assert "oversize" not in check("Hi,\n\n1 crate.\n\nThanks", raw=raw).codes


@pytest.mark.parametrize("written", [
    "Dimensions (cm): 320 x 120 x 175",
    "1 crate 126 x 47 x 69 in",
    "Crate: 3200 x 1200 x 1750 mm",
    "Kiste 1,20 x 0,80 x 1,75 m",
    "4 x 120x80x170 cm",
    'Crate 48" x 40" x 70"',
    "Crate 120 by 80 by 175 cm",
    "Abmessungen: 120/80/175 cm",
    "Height: 175 cm",
    "Crate length 3.2 m",
    "1 crate, 175 cm high",
    "Höhe: 1,75 m",
], ids=["header-cm", "inches", "mm", "metres-comma", "count-first", "inch-marks", "by", "slashes", "height-label",
        "length-label", "high", "german-height"])
def test_a_size_only_in_the_packing_list_still_needs_the_main_deck(written):
    c = check("Hi,\n\n1 crate of machine parts, 2.65 cbm. Packing list attached.\n\nThanks",
              texts=[f"Packing list\n{written}\nTotal volume (cbm): 2.65"])
    assert "oversize" in c.codes and "main deck" in c.text


@pytest.mark.parametrize("written", [
    "Dimensions (cm): 120 x 80 x 150", "120 x 80 x 160 cm", "48 x 40 x 60 in", "1200 x 800 x 1500 mm",
    "120 x 80 x 175 in total 3 pallets", "Pallet 120 x 80 cm", "Truck ready on 2026-11-25 x 3",
    "Pallets 120/80/150 cm", "Ready 2026/11/25", "Dims (cm): ready 21/11/26", "Height: 150 cm", "Max. height: 160 cm",
], ids=["fits", "at-the-limit", "60-inches", "mm-fits", "in-total-is-no-inch", "two-numbers", "date", "slashes-fit",
        "slash-date", "date-under-a-cm-header", "height-fits", "height-at-the-limit"])
def test_sizes_that_fit_or_have_no_unit_add_nothing(written):
    assert "oversize" not in check(f"Hi,\n\n{written}.\n\nThanks").codes


# 5U's real attachments: piece tables with the columns shuffled (round 10 xlsx, round 11 PDF), as the backend reads them
R10_TABLE = ("Packing Specification\nGoods description: | industrial adhesives\n"
             "Height (cm) | Gross weight (kg) | Width (cm) | Length (cm) | Pieces\n{h} | 715 | 100 | 60 | 3\n"
             "Total pieces: | 3\nTotal gross weight (kg): | 715\nTotal volume (cbm): | 2.65\n"
             "Dangerous goods: | UN1133, Class 3, Adhesives")
R11_TABLE = ("Shipper's Letter of Instruction\nGoods description: maintenance spray cans\nTotal pieces: 4\n"
             "Total gross weight (kg): 855\nPieces Length (cm) Height (cm) Width (cm) Gross weight (kg)\n4 120 {h} 60 {kg}")


@pytest.mark.parametrize("table", [
    R10_TABLE.format(h=185), R11_TABLE.format(h=175, kg=855), R11_TABLE.format(h=130, kg=7200),
    "Höhe (cm) | Länge (cm) | Breite (cm) | Anzahl | Gewicht (kg)\n185 | 120 | 80 | 2 | 900",
    "Pieces Length (in) Width (in) Height (in) Weight (lb)\n1 48 40 72 900",
    "Item | Dims L x W x H (cm) | kg\n1 | 320 x 120 x 175 | 900",
], ids=["r10-layout-tall", "r11-layout-tall", "r11-layout-heavy", "german-columns", "inch-columns", "dims-column"])
def test_an_oversize_piece_only_in_the_packing_list_table(table):
    c = check("Hi,\n\n3 pieces, 2.65 cbm, cheapest please. Packing list attached.\n\nThanks", texts=[table])
    assert "oversize" in c.codes and "main deck" in c.text


@pytest.mark.parametrize("table", [
    R10_TABLE.format(h=147), R11_TABLE.format(h=130, kg=855),
    "Pieces Length (in) Width (in) Height (in) Weight (lb)\n4 48 40 60 3000",  # 340 kg per piece, 152 cm
    "Item Pieces Length (cm) Height (cm) Width (cm)\n1 4 120 130 60",
], ids=["round-10-as-sent", "round-11-as-sent", "pounds-are-not-kg", "unknown-column"])
def test_the_real_packing_lists_fit_the_lower_deck(table):
    assert "oversize" not in check("Hi,\n\n3 pieces, cheapest please.\n\nThanks", texts=[table]).codes


@XF("a space-separated table (PDF text) with a column the reader doesn't know ('Item Pieces Length (cm) …') is "
    "skipped: without cell borders the item number can't be told from a size, and a guess invents tall pieces")
def test_a_space_table_with_an_unknown_column_is_read():
    table = "Item Pieces Length (cm) Height (cm) Width (cm)\n1 4 120 175 60"
    assert "oversize" in check("Hi,\n\n4 pieces, cheapest please.\n\nThanks", texts=[table]).codes


def test_oversize_text_off_reads_the_pieces_only(monkeypatch):
    monkeypatch.setattr(gate, "OVERSIZE_TEXT", False)
    assert "oversize" not in check("Hi,\n\nCrate 320 x 120 x 175 cm, 2.65 cbm.\n\nThanks").codes


# ---- 3. price sanity -------------------------------------------------------------------------------------------------

def test_r1_door_to_port_without_the_trucker_is_held():
    c = check("Please arrange trucking from 85748 Garching.", raw=DOOR_RAW, result=priced([AIR]))
    assert "pickup_missing" in c.codes and c.hold


def test_door_to_port_with_the_trucker_is_clean():
    c = check("Please arrange trucking from 85748 Garching.", raw=DOOR_RAW, result=priced([DOOR]))
    assert not c.hold, c.findings


@pytest.mark.parametrize("body", [
    "Terms are EXW our plant, Industriestr. 12, 85748 Garching.",
    "Please include truck pickup.",
    "Pickup from our warehouse in 70565 Stuttgart.",
    "Abholung bei uns im Lager, 70565 Stuttgart.",
    "Door-to-airport service please.",
], ids=["exw", "truck-pickup", "pickup-from-our", "abholung-bei-uns", "door-to-airport"])
def test_pickup_words_but_no_pickup_read_is_held(body):
    c = check(f"Hi,\n\n{body} 3 crates to GRU.\n\nThanks")
    assert "pickup_unread" in c.codes and c.hold


@pytest.mark.parametrize("body", [
    "The goods are ready for pickup on 2026-11-25 at FRA.",
    "We deliver to FRA ourselves, no pickup from our warehouse needed.",
    "Airport-to-airport, delivered by us to the FRA terminal.",
], ids=["ready-for-pickup", "no-pickup", "airport-to-airport"])
def test_port_to_port_words_are_not_a_pickup(body):
    assert "pickup_unread" not in check(f"Hi,\n\n{body}\n\nThanks").codes


def test_too_high_an_option_far_above_the_others_is_held_when_fastest_isnt_the_reason():
    options = THREE + [opt("Rapid Air", 6400.0, 1)]  # 2.2 × the others' median: a surcharge or weight counted twice
    c = check("Please quote.", result=priced(options, 3))  # no fastest ask, yet the backend picked the dearest
    assert "too_high" in c.codes and c.hold


def test_fastest_asked_a_dear_fastest_option_is_not_held():  # review of #143: fastest is often dearer
    options = THREE + [opt("Rapid Air", 6400.0, 1)]
    c = check("Fastest option please.", raw={"ask": "fastest"}, result=priced(options, 3))
    assert "too_high" not in c.codes and not c.hold


def test_fastest_asked_above_the_per_kg_ceiling_is_still_held():
    options = THREE + [opt("Rapid Air", 19000.0, 1)]  # EUR 26.57 per chargeable kg: above any kit rate
    c = check("Fastest option please.", raw={"ask": "fastest"}, result=priced(options, 3))
    assert "too_high" in c.codes and c.hold


def test_a_fastest_option_within_the_kits_spread_is_not_held():
    options = THREE + [opt("Rapid Air", 5200.0, 1)]  # 1.8 ×: the most two sheets differ on one kit lane
    c = check("Fastest option please.", raw={"ask": "fastest"}, result=priced(options, 3))
    assert "too_high" not in c.codes and not c.hold


def test_too_high_a_per_kg_price_multiplied_twice_on_a_bids_only_lane():
    bid = opt("Zephyr Steppe Cargo", 1751.75 * 715, 3, source="carrier_bid", chargeable=None)
    c = check("Cheapest option please.", result=priced([bid]))
    assert "too_high" in c.codes and c.hold


def test_too_low_a_per_piece_price_read_as_the_total_on_a_bids_only_lane():
    bid = opt("Zephyr Steppe Cargo", 450.0, 3, source="carrier_bid", chargeable=None)  # EUR 450 per piece × 3
    c = check("Cheapest option please.", result=priced([bid]))
    assert "too_low" in c.codes and c.hold


def test_too_low_against_a_single_other_option():
    options = [opt("Zephyr Steppe Cargo", 900.0, 3, source="carrier_bid", chargeable=None), AIR]
    c = check("Cheapest option please.", result=priced(options))
    assert "too_low" in c.codes and c.hold


def test_too_low_against_the_median_of_three_still_holds():
    c = check("Cheapest option please.", result=priced([opt("Kestrel Airways", 900.0, 5), *THREE[1:]]))
    assert "too_low" in c.codes and c.hold


def test_a_cheaper_bid_within_reason_is_not_held():
    options = [opt("Zephyr Steppe Cargo", 1900.0, 3, source="carrier_bid", chargeable=None), AIR]
    c = check("Cheapest option please.", result=priced(options))
    assert not c.hold, c.findings


def test_a_small_shipment_at_the_minimum_charge_is_not_too_high():
    small = opt("Kestrel Airways", 264.0, 5, chargeable=5.0,
                pickup={"carrier": "Huber Transporte", "rate_id": None, "total": 120.0, "transit_days": 1})
    raw = {**DOOR_RAW, "pieces": [{**BASE_RAW["pieces"][0], "count": 1, "weight": 5}], "volume": 0.02}
    c = check("1 box, pickup from 85748 Garching.", raw=raw, result=priced([small]))
    assert not c.hold, c.findings


def test_a_pickup_leg_dearer_than_the_flight_is_held():
    door = {**AIR, "total": 2400.0 + 2650.0,
            "pickup": {"carrier": "Huber Transporte", "rate_id": None, "total": 2650.0, "transit_days": 1}}
    c = check("Pickup from 85748 Garching.", raw=DOOR_RAW, result=priced([door]))
    assert "too_high" in c.codes and c.hold


SHEET_LINES = [{"label": "Freight 715 kg × 2.35", "amount": 1680.25}, {"label": "Fuel 715 kg × 0.85", "amount": 607.75},
               {"label": "Security 715 kg × 0.15", "amount": 107.25}]


def test_a_surcharge_counted_twice_in_the_breakdown_is_held():
    twice = opt("Kestrel Airways", 3003.0, 5, breakdown=[*SHEET_LINES, SHEET_LINES[1]])
    c = check("Cheapest option please.", result=priced([twice, *THREE[1:]]))
    assert "breakdown" in c.codes and c.hold


def test_a_total_that_its_breakdown_does_not_add_up_to_is_held():
    c = check("Cheapest option please.", result=priced([opt("Kestrel Airways", 2700.0, 5, breakdown=SHEET_LINES),
                                                        *THREE[1:]]))
    assert "breakdown" in c.codes and c.hold


def test_a_breakdown_that_adds_up_is_clean():
    c = check("Cheapest option please.", result=priced([opt("Kestrel Airways", 2395.25, 5, breakdown=SHEET_LINES),
                                                        *THREE[1:]]))
    assert not c.hold, c.findings


@pytest.mark.parametrize("reply,total", [
    ("Air freight EUR 2,100\nFuel EUR 310\nSecurity EUR 95\nTotal EUR 2,505", 2505.0),
    ("EUR 2,505 all-in (fuel EUR 310 and security EUR 95 included)", 2505.0),
    ("Total: 2,505.00 EUR all-in, fuel and security included\nTransit: 3 days", 2505.0),
    ("Rate EUR 2.45/kg, total EUR 1,751.75\nTransit: 3 days", 1751.75),
    ("EUR 2.45 per kg, min EUR 150\nTransit: 3 days", 1751.75),
], ids=["lines-and-total", "all-in-incl", "total-incl", "rate-and-total", "per-kg-only"])
def test_carrier_bids_never_count_a_surcharge_or_the_weight_twice(reply, total):
    assert parse_bid(reply, 715.0)["total"] == total


def test_price_sanity_v2_off_is_the_old_section_5(monkeypatch):
    monkeypatch.setattr(gate, "PRICE_SANITY_V2", False)
    bid = opt("Zephyr Steppe Cargo", 900.0, 3, source="carrier_bid", chargeable=None)
    assert not check("Cheapest option please.", result=priced([bid, AIR])).hold
    assert not check("Terms are EXW our plant, 85748 Garching.").hold
    assert check("Cheapest option please.", raw=DOOR_RAW, result=priced([AIR])).hold  # R1 still held


def test_backend_price_warnings_still_reach_the_session_log():
    c = check("Cheapest option please.", result=priced(warnings=["EUR 0.90/kg is far from the sheets' 3.10-4.20/kg"]))
    assert "price_warning" in c.codes and not c.hold


# ---- 4. review of #143: false positives cost a hold (the quote waits 240 s) or a wrong DG paragraph -----------------

def _quote(monkeypatch, tmp_path, body, raw=None, result=None):
    """The whole RFQ path with the real auto-send time: (quote text, held?). A hold is recorded, never waited for."""
    held = []
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: ({**BASE_RAW, **(raw or {})}, 0.0001))
    monkeypatch.setattr(rfq_agent, "_hold", lambda session_id, mail, api: held.append(mail["id"]) or True)
    monkeypatch.setattr(rfq_agent, "_sleep", lambda s: None)
    monkeypatch.setattr(rfq_agent, "FALLBACK_AT_SECONDS", 0.0)
    assert rfq_agent.GATE_AUTO_SEND_SECONDS == 240  # a hold would wait the full 240 s live
    api, box = GateApi(result or priced()), FixtureMailbox(tmp_path)
    mail = {"id": "m1", "thread_id": f"t-review-{abs(hash(body))}", "from": "buyer@customer.example",
            "subject": "Air freight quote", "body": body, "attachments": []}
    rfq_agent.handle_rfq(mail, box, api)
    [sent] = [s for s in box.sent if s["thread_id"] == mail["thread_id"]]
    return sent["body"], bool(held) or "needs_human" in api.events


def _papers(text):
    return all(p in text for p in DG_PAPERS)


# 1. a reference number is no UN number; 2. empty packaging is no DG
@pytest.mark.parametrize("body,language", [
    ("Our ref UN-2024-118, 3 crates of machine parts.", "en"),
    ("PO UN 4711: 3 crates of machine parts.", "en"),
    ("Unsere Referenz UN-2024-118, 3 Kisten Maschinenteile.", "de"),
    ("Rechnung UN1234, 3 Kisten Maschinenteile.", "de"),
    ("3 pallets of empty perfume bottles.", "en"),
    ("Aerosol caps (plastic, empty), 2 pallets.", "en"),
    ("Nozzles for spray cans, 3 cartons.", "en"),
    ("3 Paletten leere Parfümflaschen.", "de"),
    ("Spraydosen-Deckel, 2 Paletten.", "de"),
], ids=["ref-un-dash", "po", "referenz", "rechnung", "empty-perfume", "aerosol-caps", "nozzles", "leere-flaschen",
        "deckel"])
def test_a_reference_or_empty_packaging_is_no_dg_and_sent_at_once(body, language, monkeypatch, tmp_path):
    text, held = _quote(monkeypatch, tmp_path, f"Hi,\n\n{body} 715 kg, 2.65 cbm. Cheapest please.\n\nThanks",
                        raw={"language": language})
    assert not _papers(text) and not held


@pytest.mark.parametrize("body,language", [
    ("UN 1993, 3 drums of cleaning concentrate.", "en"),
    ("Perfume, 50 ml bottles, 3 cartons.", "en"),
    ("Parfüm in 50-ml-Flaschen, 3 Kartons.", "de"),
    ("3 Fässer Reinigungskonzentrat, UN 1993.", "de"),
], ids=["un-1993", "perfume-50ml", "parfuem-50ml", "un-1993-de"])
def test_the_real_dg_next_to_them_still_asks_for_the_papers(body, language, monkeypatch, tmp_path):
    text, _ = _quote(monkeypatch, tmp_path, f"Hi,\n\n{body} 715 kg. Cheapest please.\n\nThanks",
                     raw={"language": language})
    assert _papers(text)


# 3. fastest asked: a dear fastest option is the ask, not a part counted twice
@pytest.mark.parametrize("body,language", [("Fastest option please.", "en"), ("Bitte die schnellste Option.", "de")])
def test_fastest_asked_a_dear_fastest_option_is_sent_at_once(body, language, monkeypatch, tmp_path):
    options = [*THREE, opt("Rapid Air", 6400.0, 1)]  # 2.2 × the others' median
    text, held = _quote(monkeypatch, tmp_path, f"Hi,\n\n{body}\n\nThanks", raw={"ask": "fastest", "language": language},
                        result=priced(options, 3))
    assert "6,400.00" in text and not held


def test_fastest_asked_above_the_per_kg_ceiling_still_holds(monkeypatch, tmp_path):
    options = [*THREE, opt("Rapid Air", 19000.0, 1)]  # EUR 26.57 per chargeable kg
    _, held = _quote(monkeypatch, tmp_path, "Hi,\n\nFastest option please.\n\nThanks", raw={"ask": "fastest"},
                     result=priced(options, 3))
    assert held


# 4. the shipper brings the goods to the airport, or door words are about the destination: no pickup expected
@pytest.mark.parametrize("body,language", [
    ("We bring it to FRA ourselves, door-to-door to our customer in São Paulo please.", "en"),
    ("Door-to-door to our customer in São Paulo, DAP.", "en"),
    ("EXW our plant, we deliver it to FRA.", "en"),
    ("We will deliver the goods from our warehouse to MUC airport ourselves.", "en"),
    ("EXW, we drop them at FRA.", "en"),
    ("EXW, we deliver to MUC airport ourselves.", "en"),
    ("Ex works, delivered to your warehouse at the airport.", "en"),
    ("Ab Werk (EXW), wir liefern die Ware selbst an den Flughafen, Haus-zu-Haus bis zum Empfänger.", "de"),
    ("Wir liefern an den Flughafen FRA, Lieferung frei Haus beim Empfänger.", "de"),
    ("EXW, Anlieferung am Flughafen durch uns.", "de"),
], ids=["bring-to-fra", "door-to-door-dap", "exw-deliver-fra", "from-warehouse-to-muc", "drop-at-fra",
        "deliver-muc-ourselves", "your-warehouse", "ab-werk-selbst", "wir-liefern-fra", "anlieferung"])
def test_self_delivery_or_destination_door_words_are_sent_at_once(body, language, monkeypatch, tmp_path):
    _, held = _quote(monkeypatch, tmp_path, f"Hi,\n\n{body} 3 crates, 715 kg.\n\nThanks", raw={"language": language})
    assert not held


@pytest.mark.parametrize("body", ["Terms are EXW our plant, Industriestr. 12, 85748 Garching.",
                                  "EXW our plant 85748 Garching, we cannot bring it to the airport."])
def test_exw_at_the_plant_without_a_pickup_still_holds(body, monkeypatch, tmp_path):
    _, held = _quote(monkeypatch, tmp_path, f"Hi,\n\n{body} 3 crates, 715 kg.\n\nThanks")
    assert held  # main's INCOTERM_PICKUP reads the plant, the price has no pickup leg: pickup_missing


def test_exw_without_a_postcode_or_pickup_read_still_holds_in_the_gate():
    for body in ("EXW our plant, 3 crates.", "Abholung bei uns im Lager, 3 Kisten.", "EXW, we can't deliver to the airport."):
        assert "pickup_unread" in check(f"Hi,\n\n{body}\n\nThanks").codes


# Julien's review: a negation counts only when it governs the DG word ("no aerosols"), not the clause ("no rush")
MUST_FLAG = [
    "Not stackable perfume cartons", "We do not need insurance for the lithium batteries",
    "Please don't stack the lithium-ion batteries", "nicht stapeln Lithium-Ionen-Batterien", "no rush for the spray cans",
    "No other cargo besides the aerosols", "We have never shipped perfumes before",
    "not sure if the adhesives count as DG", "No idea whether the glue is dangerous", "Not urgent dry ice shipment",
    "No pickup needed 200 kg dry ice",
]


@pytest.mark.parametrize("body", MUST_FLAG, ids=[b[:40] for b in MUST_FLAG])
def test_a_negation_about_something_else_still_flags_dg(body, monkeypatch):
    found = bool(dg_info(body))
    monkeypatch.setattr(dg_mod, "CARGO_WORDS_V2", False)
    assert found == bool(dg_info(body))  # dg_info flags it exactly where main's reading does
    assert found or "dry ice" in body  # main's dg.py never read dry ice: the gate does
    assert gate._first_hit(gate.DG_V2, body)  # the gate on its own too
    assert asks_dg_papers(check(f"Hi,\n\nplease quote the cheapest option. {body}.\n\nThanks"))


@pytest.mark.parametrize("body", [
    "Magnetic stirrers, 2 boxes.", "Battery-free sensors.", "Non-hazardous goods, 3 pallets.", "Dry ice not required.",
    "Gefahrgut: nein", "UN-tested packaging, 3 pallets.", "No dangerous goods, no lithium batteries, no aerosols.",
    "Contains no aerosols, perfumes or lithium batteries.", "These are not dangerous goods.",
    "Es handelt sich nicht um Gefahrgut.", "Without lithium batteries.",
], ids=lambda b: b[:40])
def test_a_negation_of_the_dg_word_itself_still_counts(body):
    c = check(f"Hi,\n\nplease quote the cheapest option. {body}\n\nThanks")
    assert not c.rfq.get("dangerous_goods") and "MSDS" not in c.text, c.findings


@pytest.mark.parametrize("body", [
    "paint shop equipment", "spare parts for e-bikes", "isotope analyzers", "hand sanitizer dispensers (empty)",
    "printing ink cartridges", "fire extinguisher brackets", "oxygen cylinder regulators", "pesticide sprayers (empty)",
    "ammunition boxes (empty)", "car battery chargers", "Lithium Holdings Ltd samples", "Ceramics class 4 tiles",
    "flowers pots (ceramic)",
], ids=lambda b: b[:40])
def test_equipment_for_dg_is_no_dg_and_no_special_cargo(body, monkeypatch, tmp_path):
    assert not dg_info(body)
    c = check(f"Hi,\n\nplease quote the cheapest option. 3 pallets of {body}.\n\nThanks")
    special = {k for k, *_ in gate.SPECIAL} | {"dangerous_goods"}
    assert not (special & c.codes) and not c.hold and "MSDS" not in c.text, c.findings
    text, held = _quote(monkeypatch, tmp_path, f"Hi,\n\n3 pallets of {body}, 715 kg. Cheapest please.\n\nThanks")
    assert not _papers(text) and not held


@pytest.mark.parametrize("body", [
    "fire extinguishers, 3 pallets", "oxygen cylinders, 4 pieces", "car batteries, 2 pallets", "Li-ion tools, 3 cartons",
    "lithium battery packs, 2 cartons", "ammunition, 2 boxes", "fresh flowers, 40 boxes",
], ids=lambda b: b[:40])
def test_the_goods_themselves_still_flag(body):
    c = check(f"Hi,\n\nplease quote the cheapest option. {body}.\n\nThanks")
    assert asks_dg_papers(c) or "perishable" in c.codes or "live_animals" in c.codes, c.findings


# ---- the eval suite with every new switch off: the old cases keep their old outcome ---------------------------------

OLD_CASES = [c for c in CASES if not c.get("flags") and not c.get("known_issue")]


@pytest.mark.parametrize("case", OLD_CASES, ids=[c["name"][:50] for c in OLD_CASES])
def test_old_trap_cases_pass_with_the_new_switches_off(case, tmp_path, monkeypatch):
    for module, flag in ((gate, "CARGO_WORDS_V2"), (gate, "OVERSIZE_TEXT"), (gate, "PRICE_SANITY_V2"),
                         (rfq_agent, "FALLBACK_GATE"), (rfq_agent, "DG_FOLLOWUP")):
        monkeypatch.setattr(module, flag, False)
    test_traps.test_trap(case, tmp_path, monkeypatch)
