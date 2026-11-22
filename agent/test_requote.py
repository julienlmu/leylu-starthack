"""REQUOTE (R86/R87): the customer changes the shipment after our quote. A new weight → a new quote with one amount
and the session's quote replaced (a later "yes" books the new rate); new pieces / volume without a weight, or a
reading that does not match the mail → one question, never a guess; "also quote another shipment" → no re-quote.
Fakes only: no 5U, no gateway, no LLM."""

import booking_agent
import extract as extract_mod
import requote
from extract import to_rfq
from inbox import FixtureMailbox
from test_traps2_booking import Api as BaseApi

FIRST = ("Hello,\nplease quote air freight FRA to ORD: 3 pieces, 900 kg total, 5.2 cbm, general cargo, ready "
         "2026-11-25. Cheapest option please.\nKlaus Weidner")
RAW = {"origin": "FRA", "destination": "ORD", "ask": "cheapest", "pickup_address": None, "ready_date": "2026-11-25",
       "pieces": [{"count": 3, "length": None, "width": None, "height": None, "weight": 900, "weight_is_total": True}],
       "dim_unit": "cm", "weight_unit": "kg", "volume_unit": "m3", "volume": 5.2, "commodity": "general cargo",
       "dangerous_goods": False, "customer_reference": None, "language": "en"}
R86_RAW = {**RAW, "pieces": [{"count": 5, "length": None, "width": None, "height": None, "weight": 1317,
                              "weight_is_total": True}], "volume": 8.18}
R86 = ("Hi there,\n\nHope your day's going well! Sorry for the change-the final packing list came in, and the shipment "
       "details have changed to:\n\n5 pieces, 1317 kg gross weight, 8.18 cbm\n\nEverything else stays the same. Could you "
       "please update your offer?\n\nCheers,\nKlaus Weidner")
OLD = {"carrier": "Polaris Air Logistics", "rate_id": "R-OLD", "currency": "EUR", "total": 3120.4, "transit_days": 2,
       "source": "portal", "leg": "air"}
NEW = {"carrier": "Polaris Air Logistics", "rate_id": "R-86", "currency": "EUR", "total": 4461.28, "transit_days": 2,
       "source": "portal", "leg": "air", "chargeable_weight_kg": 1363, "breakdown": []}


def _session():
    rfq, _ = to_rfq(RAW)
    return {"id": 17, "customer": "klaus@weidner.example", "thread_id": 101, "stage": "quoted", "llm_cost_usd": 0.0001,
            "received_at": "2026-11-21T23:30:00+00:00", "rfq": {**rfq, "contact_name": "Klaus Weidner"},
            "quote": OLD, "bids": []}


class _Events(list):
    """FakeApi keeps its event kinds in `events`; the backend's events(session_id) returns the session's events."""

    def __call__(self, session_id):
        return [{"kind": "mail_in", "data": {"body": FIRST, "subject": "RFQ FRA-ORD"}}]


class Api(BaseApi):
    def __init__(self, sessions=(), result=None):
        super().__init__(sessions)
        self.events = _Events()
        self.result, self.priced = result or {"options": [NEW], "chosen": NEW, "why": "cheapest"}, []

    def price(self, rfq, bids=None, fallback=False):
        self.priced.append(rfq)
        return self.result

    def book(self, session_id, rate_id):
        self.booked.append(rate_id)
        return {"booking_reference": "BK-86AB12CD", "rate_id": rate_id, "airline": "Polaris Air Logistics",
                "price": "4461.28", "currency": "EUR", "status": "booked"}


def _mail(body, mail_id=205):
    return {"id": mail_id, "thread_id": 101, "from": "klaus@weidner.example", "subject": "Re: RFQ FRA-ORD", "body": body,
            "attachments": [], "received_at": "2026-11-21T23:31:00+00:00"}


def _run(tmp_path, monkeypatch, body, raw=R86_RAW, session=None, result=None):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (raw, 0.0001))
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "question"}, 0.00002))
    session = session or _session()
    box, api = FixtureMailbox(tmp_path), Api([session], result)
    booking_agent.handle_customer_reply(_mail(body), box, api, session)
    return box, api


def test_r86_new_figures_get_one_new_amount_and_a_yes_books_the_new_rate(tmp_path, monkeypatch):
    box, api = _run(tmp_path, monkeypatch, R86)
    [sent] = box.sent
    assert "4,461.28" in sent["body"] and "3,120.40" not in sent["body"] and sent["thread_id"] == 101
    assert "Thanks for the update." in sent["body"]
    session = api.all[17]
    assert session["stage"] == "quoted" and session["quote"]["rate_id"] == "R-86" and not session.get("needs_human")
    assert session["quote"]["replaces_total"] == 3120.4 and api.priced[-1]["ask"] == "cheapest"
    kg, m3 = extract_mod.totals(session["rfq"])
    assert (kg, m3) == (1317, 8.18) and api.booked == []
    booking_agent.handle_customer_reply(_mail("Great, please book it.", 210), box, api, api.all[17])
    assert api.booked == ["R-86"]


def test_a_new_weight_without_a_change_word_but_our_question_before_it_is_requoted(tmp_path, monkeypatch):
    session = _session()
    session["rfq"] = {**session["rfq"], "requote_asked": True, "requote_asks": 1}
    box, api = _run(tmp_path, monkeypatch, "5 pcs, 1317 kg, 8.18 cbm", session=session)
    assert "4,461.28" in box.sent[-1]["body"] and "requote_asked" not in api.all[17]["rfq"]


def test_new_pieces_and_volume_without_a_weight_ask_once_never_guess(tmp_path, monkeypatch):
    box, api = _run(tmp_path, monkeypatch, "Small change: the shipment is now 5 pieces, 8.18 cbm. Please update.")
    [sent] = box.sent
    assert "gross weight" in sent["body"] and "EUR" not in sent["body"] and api.priced == []
    assert api.all[17]["quote"]["rate_id"] == "R-OLD" and api.all[17]["rfq"]["requote_asked"]
    assert not api.all[17].get("needs_human")


def test_an_incomplete_re_read_asks_once_then_a_person(tmp_path, monkeypatch):
    missing = {**R86_RAW, "pieces": [{"count": 5, "length": None, "width": None, "height": None, "weight": None,
                                      "weight_is_total": True}]}
    box, api = _run(tmp_path, monkeypatch, R86, raw=missing)
    assert len(box.sent) == 1 and "gross weight" in box.sent[0]["body"] and api.all[17]["quote"]["rate_id"] == "R-OLD"
    booking_agent.handle_customer_reply(_mail(R86, 206), box, api, api.all[17])
    assert len(box.sent) == 1 and api.all[17]["needs_human"]  # the second unclear change: a person, no second ask


def test_a_reading_that_does_not_match_the_mail_asks_instead_of_quoting(tmp_path, monkeypatch):
    misread = {**R86_RAW, "pieces": [{"count": 5, "length": None, "width": None, "height": None, "weight": 1371,
                                      "weight_is_total": True}]}
    box, api = _run(tmp_path, monkeypatch, R86, raw=misread)
    [sent] = box.sent
    assert "4,461.28" not in sent["body"] and "gross weight" in sent["body"]
    assert api.all[17]["quote"]["rate_id"] == "R-OLD" and extract_mod.totals(api.all[17]["rfq"])[0] == 900


def test_a_lane_moved_by_the_re_read_without_the_mail_naming_it_asks(tmp_path, monkeypatch):
    box, api = _run(tmp_path, monkeypatch, R86, raw={**R86_RAW, "destination": "MDW"})
    assert "gross weight" in box.sent[0]["body"] and api.all[17]["rfq"]["destination"] == "ORD"


def test_another_shipment_is_never_a_change_of_this_one():
    rfq = _session()["rfq"]
    for text in ("Thanks! Can you also quote 2 pallets, 300 kg FRA to MIA? Updated packing list attached.",
                 "We have another shipment too: 4 pcs, 650 kg, changed ready date.",
                 "In addition, please price 1 crate 120 kg to LAX, details updated."):
        assert requote.kind(text, rfq) is None, text
    assert requote.kind("The shipment changed: 5 pallets instead of another 3, 1317 kg now.", rfq) == "requote"


def test_our_own_figures_or_a_thanks_are_no_change():
    rfq = _session()["rfq"]
    assert requote.kind("Thanks for the update. Is the 900 kg including the pallets?", rfq) is None
    assert requote.kind("Correct, 3 pieces, 900 kg, 5.2 cbm as quoted. Please hold for now.", rfq) is None
    assert requote.kind("Could you update the pickup time to 10:00?", rfq) is None


def test_other_phrasings_and_units():
    rfq = _session()["rfq"]
    assert requote.kind("Die Sendung hat sich geändert: 6 Paletten, 1.450 kg, 9,2 cbm.", rfq) == "requote"
    assert requote.kind("Weight is now 2,900 lbs, everything else unchanged.", rfq) == "requote"
    assert requote.kind("Please revise: dims are now 3 x 120x80x150 cm.", rfq) == "ask"
    assert requote.stated("1,317.50 kg and 8,18 cbm")["kg"] == [1317.5] and requote.stated("8,18 cbm")["m3"] == [8.18]


def test_requote_off_leaves_it_to_a_person(tmp_path, monkeypatch):
    monkeypatch.setattr(booking_agent, "REQUOTE", False)
    box, api = _run(tmp_path, monkeypatch, R86)
    assert box.sent == [] and api.all[17]["needs_human"] and api.all[17]["quote"]["rate_id"] == "R-OLD"


def test_a_plain_yes_after_our_figures_question_never_books_the_old_rate(tmp_path, monkeypatch):
    box, api = _run(tmp_path, monkeypatch, "Small change: the shipment is now 5 pieces, 8.18 cbm. Please update.")
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "accept"}, 0.00002))
    booking_agent.handle_customer_reply(_mail("Yes, please book it.", 206), box, api, api.all[17])
    assert api.booked == [] and api.all[17]["needs_human"] and len(box.sent) == 1


def test_a_yes_with_a_new_weight_gets_the_new_quote_first(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (R86_RAW, 0.0001))
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "accept"}, 0.00002))
    session = _session()
    box, api = FixtureMailbox(tmp_path), Api([session])
    booking_agent.handle_customer_reply(_mail("Yes, book it, but the weight changed: 5 pieces, 1317 kg, 8.18 cbm."),
                                        box, api, session)
    assert api.booked == [] and "4,461.28" in box.sent[-1]["body"] and api.all[17]["quote"]["rate_id"] == "R-86"


def test_another_shipment_stays_one_even_with_instead():
    rfq = _session()["rfq"]
    assert requote.kind("Also need to ship 300 kg next week to JFK, updated: quote it instead of sea freight.", rfq) is None
    assert requote.kind("Updated: can you quote a new shipment, 3 pallets, 950 kg FRA to ORD?", rfq) is None
    assert requote.kind("We have one more pallet, please update the quote to 4 pallets, 1200 kg.", rfq) == "requote"


def test_the_figures_question_goes_out_in_the_customers_language_without_digits():
    import re
    import short_mail
    assert set(requote.ASK) == set(short_mail.HI)
    assert not any(re.search(r"\d", text) for text in requote.ASK.values())
    rfq = {**_session()["rfq"], "language": "fr"}
    assert requote.ask_text(rfq).startswith("Bonjour Klaus,") and "poids brut" in requote.ask_text(rfq)
    assert requote.ask_text({**rfq, "language": "ko"}).startswith("Hi Klaus,")
