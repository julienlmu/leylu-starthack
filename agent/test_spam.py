from router import route

CARRIERS = {"lumen-air-cargo@hackloop.mail"}


def mail(sender, subject, body):
    return {"from": sender, "subject": subject, "body": body, "attachments": []}


def test_spam_and_phishing_are_ignored():
    for subject, body in [
        ("Our November newsletter", "Click here for 50% off! https://deals.example.com Unsubscribe below."),
        ("Action required", "Dear customer, please update your bank details at http://secure-bank.example.com today."),
        ("Congratulations!", "You are the lottery winner of a 1,000,000 EUR prize. Reply with your account number."),
        ("Grow your traffic", "We offer SEO and backlinks for your website, see www.seo-shop.example"),
    ]:
        assert route(mail("promo@hackloop.mail", subject, body), CARRIERS, False) == "other", subject


def test_out_of_office_replies_are_ignored_also_from_customers_and_carriers():
    ooo = "I am out of the office until Monday with limited access to email."
    assert route(mail("buyer@customer.example", "Automatic reply: Your quote", ooo), CARRIERS, True) == "other"
    assert route(mail("lumen-air-cargo@hackloop.mail", "Out of Office: Rate request FRA-JFK", ooo), CARRIERS,
                 True) == "other"  # not a carrier bid: must not end the bid wait or be parsed as an offer
    assert route(mail("MAILER-DAEMON@hackloop.mail", "Undeliverable: Rate request", "550 user unknown"), CARRIERS,
                 False) == "other"


def test_real_requests_are_never_spam():
    rfq_with_footer = ("Hi, could you quote air freight FRA to JFK, 3 pallets, 715 kg, 2.65 cbm, ready Monday?\n\n"
                       "--\nTo unsubscribe from our newsletter click here: https://acme.example/unsubscribe")
    assert route(mail("buyer@acme.example", "Air freight quote to JFK", rfq_with_footer), CARRIERS, False) == "rfq"
    german = "Hallo, bitte um ein Angebot für Luftfracht ab München nach ORD, 4 Paletten, 855 kg. Abholung in 80331."
    assert route(mail("einkauf@firma.example", "Anfrage Luftfracht", german), CARRIERS, False) == "rfq"
    assert route(mail("buyer@acme.example", "RE: Your quote", "Yes please, go ahead and book it."), CARRIERS,
                 True) == "customer_reply"
    assert route(mail("lumen-air-cargo@hackloop.mail", "RE: Rate request FRA-JFK",
                      "Total: 1234.00 EUR\nTransit: 2 days\nRate ID: R-1"), CARRIERS, True) == "carrier_bid"
