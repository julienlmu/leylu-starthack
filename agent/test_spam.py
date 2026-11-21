import json
from pathlib import Path

from router import is_spam, route

REAL = json.loads((Path(__file__).parent / "evals" / "real_rfqs_day1.json").read_text())


def test_no_real_rfq_of_day_one_is_spam():
    for m in REAL:
        assert not is_spam({"subject": m["subject"], "body": m["body"], "attachments": [1] if m["attachments"] else []}), m["session"]


def test_review_probes_and_short_rfqs_are_not_spam():
    for body in ("Hi, special offer for you: please quote 2 pallets, 300 kg MUC-JFK.",
                 "Out of office until Monday. Meanwhile please send the quote for FRA to ORD, 120 kg.",
                 "Congratulations on the new office! Could you quote air freight to DEL, 3 boxes?",
                 "PDF is password protected, password: freight2026. Please send your best rate.",
                 "Please send us a quote, see attached packing list. Our portal login is in the SLI."):
        assert not is_spam({"subject": "", "body": body}), body
    assert not is_spam({"subject": "Newsletter", "body": "unsubscribe", "attachments": [{"id": 1}]})


def test_spam_and_out_of_office_without_a_shipment_are_spam():
    for subject, body in (("Limited-time offer", "Get 50% off our SEO backlinks package. Click here to buy now!"),
                          ("Automatic reply", "I am out of office until 2 December with no access to email."),
                          ("Account suspended", "Verify your account within 24 hours or it will be locked.")):
        mail = {"from": "promo@spam.example", "subject": subject, "body": body, "thread_id": 1}
        assert is_spam(mail) and route(mail, set(), known_thread=False) == "spam"


def test_auto_replies_in_our_threads_are_ignored():
    from router import route
    carriers = {"lumen-air-cargo@hackloop.mail"}
    ooo = {"body": "I will not be available until Monday. For urgent matters contact my colleague.", "attachments": []}
    # a customer's out-of-office in our quote thread: not a decline (the "not" would read as one)
    assert route({**ooo, "from": "buyer@acme.example", "subject": "Automatic reply: Your air freight quote"},
                 carriers, True) == "other"
    # a carrier's out-of-office in our bid thread: not an offer
    assert route({**ooo, "from": "lumen-air-cargo@hackloop.mail", "subject": "Out of Office: Rate request FRA-JFK"},
                 carriers, True) == "other"
    assert route({**ooo, "from": "MAILER-DAEMON@hackloop.mail", "subject": "Undeliverable: Rate request"},
                 carriers, True) == "other"
    # a person who mentions being away still gets read normally
    assert route({"from": "buyer@acme.example", "subject": "RE: Your air freight quote",
                  "body": "I'm out of office tomorrow, please go ahead and book it.", "attachments": []},
                 carriers, True) == "customer_reply"
    assert route({"from": "lumen-air-cargo@hackloop.mail", "subject": "RE: Rate request FRA-JFK",
                  "body": "Total: 1234.00 EUR\nTransit: 2 days\nRate ID: R-1", "attachments": []},
                 carriers, True) == "carrier_bid"


def test_spam_holes_closed_without_dropping_real_rfqs():
    from router import route
    def m(subject, body, att=()):
        return {"from": "x@hackloop.mail", "subject": subject, "body": body, "attachments": list(att)}
    # holes: "you to win" read as an IATA pair, "interest rate" as a freight rate, any attachment as an RFQ
    assert route(m("Congratulations", "We invite you to win a prize! Click here."), set(), False) == "spam"
    assert route(m("Investment opportunity", "Lock in a great interest rate now, click here."), set(), False) == "spam"
    assert route(m("Invoice overdue", "Your invoice overdue, wire transfer today.", [{"filename": "inv.zip"}]),
                 set(), False) == "spam"
    # real requests stay requests
    for subject, body, att in [
        ("Rate request", "Please send your rate for FRA-JFK", []),
        ("quote", "please quote frankfurt to chicago, see attached packing list", [{"filename": "pl.xlsx"}]),
        ("RFQ", "rates from Hamburg to Dubai please, 2 pallets", []),
        ("Shipment", "air freight to GRU, invoice attached for customs, bank details below", [{"filename": "i.pdf"}]),
    ]:
        assert route(m(subject, body, att), set(), False) == "rfq", subject



def test_an_attachment_protects_unless_it_is_an_executable_or_archive():
    """Review of #150: an inquiry PDF plus a payment word was dropped as spam."""
    for body in ("Please find our inquiry attached. Payment terms: wire transfer within 30 days.",
                 "Our RFQ is attached. Please confirm your bank details for the invoice."):
        assert not is_spam({"subject": "Inquiry", "body": body, "attachments": [{"id": 1, "filename": "request.pdf"}]})
        assert not is_spam({"subject": "Inquiry", "body": body, "attachments": [{"id": 1, "filename": "PL_123.xlsx"}]})
    phish = {"subject": "Invoice overdue", "body": "Invoice overdue: open the attachment and confirm the wire transfer.",
             "attachments": [{"id": 1, "filename": "invoice.zip"}]}
    assert is_spam(phish)
