"""Test emails to judge the humanizer by eye: realistic customer mails in very different styles and languages, and the
exact reply our agent writes to each, made by the real RFQ/booking/tracking code. Offline: the model's reading of each
mail is given (what extract.py would return), prices are fixed, nothing is sent, no gateway call.

    cd agent && uv run python evals/humanizer_samples.py > /tmp/samples.md
"""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QUOTE_STYLE", "short")  # the live style
os.environ["LINK_READ"] = "off"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract as extract_mod  # noqa: E402
import quote_style  # noqa: E402
import rfq_agent  # noqa: E402
import templates  # noqa: E402
from inbox import FixtureMailbox  # noqa: E402

BASE = {"origin": "MUC", "destination": "JFK", "ask": None, "pickup_address": None, "ready_date": "2026-11-25",
        "pieces": [{"count": 3, "length": 120, "width": 80, "height": 110, "weight": 640, "weight_is_total": True}],
        "dim_unit": "cm", "weight_unit": "kg", "volume_unit": "m3", "volume": None, "commodity": "machine parts",
        "dangerous_goods": False, "customer_reference": None, "language": "en"}
OPTION = {"source": "portal", "carrier": "Lumen Air Cargo", "rate_id": "R-7", "currency": "EUR", "total": 2184.6,
          "transit_days": 2, "valid_until": "2026-11-28", "chargeable_weight_kg": 640, "breakdown": [], "pickup": None}
DOOR = {**OPTION, "total": 2391.1, "pickup": {"carrier": "Huber Transporte", "rate_id": None, "total": 96.0, "transit_days": 1}}

RFQS = [  # (title, mail body, what the model reads, price)
    ("Formal English", "Dear Sir or Madam,\n\nWe would be grateful for your quotation for the following shipment from "
     "Munich (MUC) to New York (JFK): 3 pallets of machine parts, 120 x 80 x 110 cm each, 640 kg in total, ready on "
     "25 November.\n\nYours faithfully,\nAnna Meyer\nPurchasing, Meyer Maschinenbau GmbH", BASE, OPTION),
    ("Same request, slang + emoji (the reply must be identical in style)", "yo 👋 need a price asap lol\n3 pallets machine "
     "parts MUC→JFK, 120x80x110cm, 640kg total, ready 25 nov 🙏🙏\n\nthx\nAnna Meyer", BASE, OPTION),
    ("Same request, ALL CAPS and rude", "YOUR LAST QUOTE WAS A JOKE. 3 PALLETS MUC TO JFK, 120X80X110 CM, 640 KG TOTAL, "
     "READY 25 NOV. DO BETTER.\n\nRegards\nAnna Meyer", BASE, OPTION),
    ("German, door pickup", "Sehr geehrte Damen und Herren,\n\nbitte um Angebot: 2 Kisten Ersatzteile, 95 x 60 x 70 cm, "
     "je 180 kg, Abholung Industriestr. 12, 85748 Garching, nach Chicago (ORD), bereit am 26.11.\n\nMit freundlichen "
     "Grüßen\nJonas Kessler",
     {**BASE, "destination": "ORD", "pickup_address": "Industriestr. 12, 85748 Garching", "language": "de",
      "commodity": "Ersatzteile", "pieces": [{"count": 2, "length": 95, "width": 60, "height": 70, "weight": 180,
                                              "weight_is_total": False}]}, DOOR),
    ("French, dangerous goods (lithium batteries UN3480)", "Bonjour,\n\nPouvez-vous nous faire une offre pour 4 colis de "
     "batteries lithium-ion UN3480, classe 9, 60 x 40 x 40 cm, 220 kg au total, de FRA à Montréal (YUL) ?\n\nCordialement,"
     "\nClaire Dubois",
     {**BASE, "origin": "FRA", "destination": "YUL", "language": "fr", "commodity": "lithium-ion batteries UN3480",
      "dangerous_goods": True, "pieces": [{"count": 4, "length": 60, "width": 40, "height": 40, "weight": 220,
                                            "weight_is_total": True}]}, {**OPTION, "total": 1870.4}),
    ("Turkish, casual", "Merhaba,\n\nIST'den JFK'ye 5 koli tekstil numunesi, toplam 150 kg, 50x40x30 cm. En hızlı seçenek "
     "lazım. Teşekkürler!\n\nSelamlar\nDeniz Yılmaz",
     {**BASE, "origin": "IST", "language": "tr", "ask": "fastest", "commodity": "tekstil numunesi",
      "pieces": [{"count": 5, "length": 50, "width": 40, "height": 30, "weight": 150, "weight_is_total": True}]},
     {**OPTION, "total": 1412.0, "transit_days": 1}),
    ("Spanish mail asking for an English answer", "Hola,\n\nnecesitamos precio para 2 palés de repuestos de MAD a Miami "
     "(MIA), 300 kg en total, 120 x 80 x 100 cm.\n\nPS: please answer in English, our team in Miami will book it.\n\n"
     "Saludos,\nLucía Romero",
     {**BASE, "origin": "MAD", "destination": "MIA", "language": "es", "reply_language": "en",
      "pieces": [{"count": 2, "length": 120, "width": 80, "height": 100, "weight": 300, "weight_is_total": True}]},
     {**OPTION, "total": 1655.25}),
    ("Japanese", "ご担当者様\n\n成田(NRT)からフランクフルト(FRA)まで、精密機器3箱、合計210kg、各60x50x40cmの航空輸送の"
     "お見積もりをお願いします。\n\nよろしくお願いいたします。\n佐藤 健",
     {**BASE, "origin": "NRT", "destination": "FRA", "language": "ja", "commodity": "精密機器",
      "pieces": [{"count": 3, "length": 60, "width": 50, "height": 40, "weight": 210, "weight_is_total": True}]},
     {**OPTION, "total": 2950.0, "transit_days": 3}),
    ("Weight without a unit (we ask, never guess kg or lbs)", "Hi,\n\nplease quote 3 boxes MUC to JFK, 715 total, "
     "60x40x40 cm.\n\nThanks,\nTom Becker",
     {**BASE, "weight_unit": "kg", "pieces": [{"count": 3, "length": 60, "width": 40, "height": 40, "weight": 715,
                                                "weight_is_total": True}]}, OPTION),
]


class Api:
    def __init__(self, price):
        self.price_result, self.events = price, []

    def create_session(self, *a, **k):
        return 1

    def session(self, session_id):
        return {"paused": False, "needs_human": False, "quote": None}

    def sessions(self, stage=None):
        return []

    def update(self, *a, **k):
        pass

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append((kind, text))

    def price(self, rfq, bids=None, fallback=False):
        return {"options": [self.price_result], "chosen": self.price_result, "why": "cheapest"}


def block(title: str, inbound: str, reply: str) -> str:
    quote = lambda text: "\n".join("> " + line if line else ">" for line in text.splitlines())
    return f"## {title}\n\n**Customer wrote:**\n\n{quote(inbound)}\n\n**Our reply:**\n\n```text\n{reply}\n```\n"


def main() -> None:
    out = ["# Humanizer test emails\n", "Generated by `agent/evals/humanizer_samples.py` with the live style "
           f"(QUOTE_STYLE={quote_style.QUOTE_STYLE}). Real agent code, fixed prices, nothing sent.\n"]
    with TemporaryDirectory() as folder:
        for n, (title, body, raw, price) in enumerate(RFQS):
            extract_mod.extract = lambda mail, model=None, raw=raw: ({**raw}, 0.0)
            box = FixtureMailbox(Path(folder) / str(n))
            rfq_agent.handle_rfq({"id": f"m{n}", "thread_id": f"t{n}", "from": "customer@example.com",
                                  "subject": "Request for quotation", "body": body}, box, Api(price))
            reply = box.sent[-1]["body"] if box.sent else "(no mail: " + "; ".join(t for _, t in Api(price).events) + ")"
            out.append(block(title, body, reply))
    rfq = {"contact_name": "Anna Meyer", "language": "en", "origin": "MUC", "destination": "JFK", "ask": "cheapest",
           "pieces": [{"count": 3, "weight_kg": 213.3}], "ready_date": "2026-11-25", "pickup": None}
    quote = {**OPTION}
    booking = {"booking_reference": "BK-48213", "airline": "Lumen Air Cargo", "status": "requested",
               "rate_id": "R-7", "total": 2184.6, "currency": "EUR"}
    session = {"rfq": rfq, "quote": quote, "booking": {**booking, "status": "confirmed", "flight": "LA 402",
                                                       "departure": "2026-11-26"}}
    out.append(block("Customer accepts: \"sounds good, go ahead and book it\"", "sounds good, go ahead and book it\n\nAnna",
                     templates.booking_text(rfq, booking)))
    out.append(block("Airline confirms the booking (mail to the customer)", "(airline: Booking BK-48213 confirmed)",
                     templates.booking_confirmed_text(session)))
    out.append(block("Tracking question", "Hi, where is our shipment BK-48213? Thanks, Anna",
                     templates.tracking_text(session)))
    out.append(block("Question about the open quote", "Does that price include fuel and security? And when would it "
                     "arrive?\n\nAnna", quote_style.quote_summary_text(rfq, quote, "Does that price include fuel?")))
    out.append(block("Price changed before booking (we ask again, never book a new price unasked)", "yes please book",
                     templates.reprice_text(rfq, {**quote, "total": 2231.9})))
    print("\n".join(out))


if __name__ == "__main__":
    main()
