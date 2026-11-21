import pytest

import bids


@pytest.mark.parametrize("reply, asks", [
    ("Hello,\n\nis the cargo stackable? Then we can send you our rate.\n\nBest regards", ["is the cargo stackable"]),
    ("Could you confirm the commodity and whether it is dangerous goods?",
     ["could you confirm the commodity and whether it is dangerous goods"]),
    ("Dear team, what is the exact pickup address?", ["dear team, what is the exact pickup address"]),
])
def test_a_carrier_question_instead_of_a_bid_is_an_info_request(reply, asks):
    assert bids.info_request(reply) == asks


@pytest.mark.parametrize("reply", [
    "Sorry, we do not serve this lane. Anything else we can help with?",  # a decline is no question
    "Total: 900.00 EUR\nTransit: 2 days\nShall we book?",  # a bid with a question is a bid
    "Thanks, noted. How can we help further?",
    "OK.",
])
def test_declines_bids_and_pleasantries_are_no_info_request(reply):
    assert bids.info_request(reply) == []


def test_carrier_questions_off(monkeypatch):
    monkeypatch.setattr(bids, "CARRIER_QUESTIONS", False)
    assert bids.info_request("Is the cargo stackable?") == []
    assert bids.info_request("To quote we need:\n- the pickup postcode") == ["the pickup postcode"]  # unchanged


def test_a_bid_with_a_question_or_a_lowercase_currency_is_still_a_bid():
    import bids
    for reply in ("Hi, we can do it for 980 Euro, transit 1 day, rate id AB12. Do you want us to proceed?",
                  "Our offer: 1450 eur. Is it stackable?", "Total: 1234 Euro\nTransit 2 days\nIs the cargo stackable?",
                  "Our rate: 1,450.00 all-in, transit 2 days. Is the cargo stackable?", "Can do 1450 euros, 2 days. OK for you?"):
        assert bids.info_request(reply) == [], reply
    assert bids._money("neuro 5 and 2 Europallets") == set()  # "euro" only as a word
