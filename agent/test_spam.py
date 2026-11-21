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
