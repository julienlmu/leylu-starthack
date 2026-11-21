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
                          ("Account suspended", "Verify your account within 24 hours or it will be locked."),
                          ("Quick question about your quoting process",  # R55 (20:21 UTC)
                           "Hi there,\n\nI noticed your company handles air export quotes. Most forwarders we talk to "
                           "lose 30% of their RFQs because replies are too slow.\n\nFreightSoft Pro answers every RFQ in "
                           "under 60 seconds. Could we book 15 minutes this week to show you a demo? Just reply with a "
                           "time that suits you.\n\nCheers\nTom Becker\nAccount Executive, FreightSoft Pro")):
        mail = {"from": "promo@spam.example", "subject": subject, "body": body, "thread_id": 1}
        assert is_spam(mail) and route(mail, set(), known_thread=False) == "spam"
