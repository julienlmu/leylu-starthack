import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from router import route
C = {"lumen-air-cargo@hackloop.mail"}
def m(s, b, f="x@hackloop.mail", att=()): return {"from": f, "subject": s, "body": b, "attachments": [{"id": i, "filename": a} for i, a in enumerate(att)]}
SPAM = [  # should be ignored (spam / other)
 ("freight newsletter", m("Our new air freight rates", "Dear partner, check our special offer on air freight from FRA. Book now! Unsubscribe here.")),
 ("competitor promo", m("Cheap shipping", "Save 30% on your next shipment with ShipFast. Get a free quote today! Click here.")),
 ("customs phishing", m("Your shipment is on hold", "Your parcel is held at customs. Pay the 2.99 EUR fee here: http://pay-customs.example to release your shipment.")),
 ("fake tracking phishing", m("Delivery failed", "We could not deliver your package. Confirm your address and pay here http://track-now.example")),
 ("419 scam", m("Business proposal", "I am Mrs. Grace, I have an inheritance of 4.5 million USD and need a trusted partner. God bless.")),
 ("german spam", m("Sie haben gewonnen!", "Herzlichen Glückwunsch, Sie haben ein iPhone gewonnen. Jetzt klicken und Gewinn abholen. Abmelden")),
 ("french spam", m("Offre spéciale", "Félicitations! Cliquez ici pour profiter de -50% aujourd'hui. Se désabonner")),
 ("spanish spam", m("Oferta exclusiva", "¡Felicidades! Haga clic aquí para reclamar su premio. Darse de baja")),
 ("SaaS sales pitch", m("Partnership proposal", "We help freight forwarders automate shipments with our TMS. Book a demo: www.tms-demo.example")),
 ("job application", m("Application", "Dear Sir, I would like to apply for a job as a driver in your company. My CV is attached.", att=["cv.pdf"])),
 ("calendar invite", m("Invitation: Quarterly review @ Mon 10:00", "You have been invited to a meeting. Join with Google Meet: https://meet.example/abc")),
 ("OOO unknown thread w/ shipment words", m("Automatic reply: Rate request", "I am out of office. For urgent shipment requests please contact ops@forwarder.example")),
 ("bounce unknown thread", m("Undeliverable: Air freight quote", "Delivery has failed to these recipients", f="mailer-daemon@hackloop.mail")),
 ("subject-only quote phishing", m("RE: Quote #4471", "Please review the attached invoice and verify your account here: http://login.example", att=["invoice.pdf"])),
 ("diet spam with kg", m("Lose 10 kg fast", "Lose 10 kg in two weeks! Limited time offer, click here.")),
 ("crypto", m("Investment opportunity", "Double your bitcoin in 7 days. Act now: www.coin.example")),
 ("empty body", m("Hello", "")),
 ("link only", m("Hi", "https://bit.ly/3xYz")),
]
REAL = [  # must be handled as RFQ / reply
 ("short rfq + footer", m("Price request", "Hi, we need a price for 3 boxes to Toronto. Thanks\n--\nClick here to unsubscribe from our newsletter")),
 ("rfq words-only numbers", m("Air freight", "Could you quote three pallets weighing about two tons from Munich to Chicago?\nUnsubscribe | Newsletter")),
 ("rfq only attachment", m("Request", "Please see attached.", att=["packing_list.xlsx"])),
 ("rfq german", m("Anfrage", "Bitte um ein Angebot für 4 Paletten, 855 kg, Abholung Lüneburg nach YYZ.")),
 ("rfq french", m("Demande de devis", "Merci de nous faire un devis pour 2 palettes, 300 kg, de Paris à Montréal.")),
 ("rfq spanish", m("Cotización", "Necesitamos una cotización para 5 cajas, 120 kg, de Madrid a Bogotá.")),
 ("rfq turkish", m("Fiyat teklifi", "Istanbul'dan Frankfurt'a 3 palet, 450 kg için fiyat teklifi rica ederiz.")),
 ("rfq prize trophies", m("Quote", "Please quote 2 pallets of prize trophies, 180 kg, MUC to DXB. Congratulations on your growth!")),
 ("rfq with marketing signature", m("RFQ FRA-ORD", "Please quote 500 kg FRA to ORD.\n\nVisit our webinar on Tuesday! Special offer for subscribers. Unsubscribe")),
 ("rfq with link to specs", m("Quote request", "Please quote air freight for the goods described here https://specs.example/item1, 2 crates, 400 kg, to JFK.")),
 ("rfq mentions invoice + bank", m("Shipment", "air freight to GRU, 300 kg, invoice attached for customs, bank details below", att=["i.pdf"])),
 ("rfq forwarded", m("FW: transport request", "Please quote the shipment below.\n\n-----Original Message-----\nFrom: Anna\nWe need 2 pallets 600 kg to SIN.")),
 ("rfq no numbers polite", m("Air freight to Nairobi", "Could you please send us your best offer for air freight to Nairobi? Details: machine parts, ready next week. Unsubscribe")),
]
holes = 0
for name, mail in SPAM:
    got = route(mail, C, False)
    ok = got in ("spam", "other"); holes += not ok
    print(("ok   " if ok else "SLIPS") + f" spam  {name}: {got}")
for name, mail in REAL:
    got = route(mail, C, False)
    ok = got == "rfq"; holes += not ok
    print(("ok   " if ok else "LOST!") + f" real  {name}: {got}")
real = json.loads((Path(__file__).resolve().parent / "real_rfqs_day1.json").read_text())
from router import is_spam
lost = [r["session"] for r in real if is_spam({"subject": r["subject"], "body": r["body"], "attachments": [1] if r["attachments"] else []})]
print(f"day-one real RFQs: {len(real)}, wrongly spam: {lost}")
