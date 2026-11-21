import booking_agent
from booking_agent import handle_booking_confirmed, handle_customer_reply, latest_text, read_intent
from inbox import FixtureMailbox
from router import route
from tracking_agent import handle_tracking

BOOKING = {"booking_reference": "BK-1A2B3C4D", "team_reference": "17", "rate_id": "R-1", "airline": "SkyAir",
           "airline_code": "SK", "price": "1856.00", "currency": "EUR", "status": "booked"}
SESSION = {"id": 17, "customer": "buyer@customer.example", "thread_id": 101, "stage": "quoted", "llm_cost_usd": 0.0001,
           "rfq": {"origin": "MUC", "destination": "JFK"},
           "quote": {"carrier": "SkyAir", "rate_id": "R-1", "currency": "EUR", "total": 1856.0, "transit_days": 2}}
REPLY = {"id": 105, "thread_id": 101, "from": "buyer@customer.example", "subject": "Re: RFQ MUC-JFK",
         "body": "Yes please, go ahead.\n\nOn Sat, team wrote:\n> Just reply to this email and we'll book it"}


class FakeApi:
    def __init__(self, sessions=()):
        self.sessions = {s["id"]: dict(s) for s in sessions}
        self.updates, self.events, self.booked, self.lookups, self.data = [], [], [], [], {}

    def session(self, session_id):
        return self.sessions[session_id]

    def booked_sessions(self):
        return [s for s in self.sessions.values() if s.get("booking")]

    def find(self, thread_id=None, reference=None):
        self.lookups.append(reference)
        return next((s for s in self.sessions.values()
                     if reference in (s.get("booking") or {}).get("booking_reference", "")), None)

    def update(self, session_id, **fields):
        self.updates.append(fields)
        self.sessions[session_id].update(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append(kind)
        self.data[kind] = data

    def book(self, session_id, rate_id):
        self.booked.append(rate_id)
        return BOOKING


def test_latest_text_drops_our_quoted_mail():
    assert latest_text(REPLY["body"]).strip() == "Yes please, go ahead."


def test_read_intent_uses_rules_for_clear_answers_and_the_llm_otherwise(monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "question"}, 0.00003))
    assert read_intent(REPLY["body"]) == ("accept", 0.0)
    assert read_intent("No thanks, that's too expensive.") == ("decline", 0.0)
    assert read_intent("Looks ok, but can you do it cheaper?") == ("question", 0.00003)


def test_accepted_quote_is_booked_by_rate_id_and_confirmed_in_thread(tmp_path):
    box, api = FixtureMailbox(tmp_path), FakeApi([SESSION])
    handle_customer_reply(REPLY, box, api, SESSION)
    assert api.booked == ["R-1"]
    [sent] = box.sent
    assert sent["thread_id"] == 101 and "BK-1A2B3C4D" in sent["body"]
    assert api.sessions[17]["stage"] == "booked" and api.sessions[17]["outcome"] == "won"
    assert api.events == ["mail_in", "accepted", "booked"]


def test_airline_confirmation_updates_the_crm_and_informs_the_customer(tmp_path):
    box, api = FixtureMailbox(tmp_path), FakeApi([{**SESSION, "stage": "booked", "booking": BOOKING}])
    mail = {"id": 120, "thread_id": 120, "from": "ops@skyair.example", "subject": "Booking BK-1A2B3C4D confirmed",
            "body": "…", "attachments": []}
    assert route(mail, {"ops@skyair.example"}, known_thread=False) == "booking_confirmed"
    assert handle_booking_confirmed(mail, box, api)
    assert api.sessions[17]["booking"]["status"] == "confirmed"
    assert box.sent[0]["thread_id"] == 101  # told the customer in their own thread
    assert api.data["status_sent"]["body"] == box.sent[0]["body"]  # the UI shows that mail in the thread


def test_airline_confirmation_survives_a_null_status_list(tmp_path):
    session = {**SESSION, "stage": "booked", "booking": BOOKING, "status_updates": None}
    box, api = FixtureMailbox(tmp_path), FakeApi([session])
    mail = {"id": 121, "thread_id": 121, "from": "ops@skyair.example", "subject": "Booking BK-1A2B3C4D confirmed",
            "body": "…", "attachments": []}
    assert handle_booking_confirmed(mail, box, api)
    assert [u["text"] for u in api.sessions[17]["status_updates"]] == ["Booking BK-1A2B3C4D confirmed by the airline"]


def test_tracking_question_is_answered_from_the_crm(tmp_path):
    session = {**SESSION, "stage": "booked", "booking": {**BOOKING, "status": "confirmed"}}
    box, api = FixtureMailbox(tmp_path), FakeApi([session])
    mail = {"id": 130, "thread_id": 130, "from": "tracking@hackloop.mail",
            "subject": "Status BK-1A2B3C4D", "body": "Where is shipment BK-1A2B3C4D right now?"}
    handle_tracking(mail, box, api)
    [answer] = box.sent
    assert "BK-1A2B3C4D" in answer["body"] and "confirmed by the airline" in answer["body"]
    assert api.events == ["tracking_answer"]
    assert api.data["tracking_answer"]["body"] == answer["body"]


def test_tracking_question_for_an_unknown_booking_asks_for_the_reference(tmp_path):
    box, api = FixtureMailbox(tmp_path), FakeApi()
    mail = {"id": 131, "thread_id": 131, "from": "tracking@hackloop.mail", "subject": "Status?",
            "body": "Where is BK-ZZZZZZZZ?"}
    handle_tracking(mail, box, api)
    assert "starts with BK-" in box.sent[0]["body"]


def test_two_acceptances_at_once_book_once_and_mail_once(tmp_path):
    import threading
    import time

    class SlowPortalApi(FakeApi):
        def book(self, session_id, rate_id):
            time.sleep(0.2)  # the portal call takes a moment: plenty of time for the second reply to race in
            return super().book(session_id, rate_id)

    box, api = FixtureMailbox(tmp_path), SlowPortalApi([SESSION])
    second = {**REPLY, "id": 106, "body": "Yes, book it please."}
    threads = [threading.Thread(target=handle_customer_reply, args=(m, box, api, SESSION)) for m in (REPLY, second)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert api.booked == ["R-1"]
    assert len(box.sent) == 1


def test_a_pause_during_booking_keeps_the_booking_and_holds_the_mail(tmp_path):
    class PauseWhileBookingApi(FakeApi):
        def book(self, session_id, rate_id):
            self.sessions[session_id]["paused"] = True  # a person pauses the session while the portal books
            return super().book(session_id, rate_id)

    box, api = FixtureMailbox(tmp_path), PauseWhileBookingApi([SESSION])
    handle_customer_reply(REPLY, box, api, SESSION)
    assert api.sessions[17]["booking"]["booking_reference"] == "BK-1A2B3C4D"
    assert api.sessions[17]["stage"] == "booked"
    assert box.sent == []


def test_thanks_after_the_booking_need_no_person():
    booked = {**SESSION, "stage": "booked", "booking": BOOKING}
    api = FakeApi([booked])
    thanks = {**REPLY, "subject": "Re: Your air freight booking",
              "body": "Thank you for confirming the booking.\n\n> Booking BK-1A2B3C4D, any questions?"}
    handle_customer_reply(thanks, FixtureMailbox("."), api, booked)
    assert "needs_human" not in api.events and not any(u.get("needs_human") for u in api.updates)
    question = {**REPLY, "body": "Thanks! When will it be picked up?"}
    handle_customer_reply(question, FixtureMailbox("."), api, booked)
    assert "needs_human" in api.events



def test_after_a_booking_only_a_plain_thank_you_stays_quiet(tmp_path):
    booked = {**SESSION, "stage": "booked", "booking": BOOKING}
    for body, person in (("Thank you, that was quick!", False), ("Vielen Dank für die schnelle Buchung.", False),
                         ("Please cancel the booking.", True), ("Thanks, but please cancel it.", True),
                         ("Please change the pickup date to Monday.", True), ("Kindly send me the invoice.", True)):
        box, api = FixtureMailbox(tmp_path), FakeApi([booked])
        handle_customer_reply({**REPLY, "body": body}, box, api, booked)
        assert ("needs_human" in api.events) is person, body
        assert box.sent == [] and api.booked == [], body  # never a mail or a second booking



def test_a_pending_booking_is_retried_on_the_next_yes_and_tracking_doesnt_crash(tmp_path):
    # Backend #36: after a lost portal answer the session keeps {pending_rate_id}; only a BK- reference means booked.
    pending = {**SESSION, "booking": {"pending_rate_id": "R-fresh"}}
    box, api = FixtureMailbox(tmp_path), FakeApi([pending])
    handle_customer_reply(REPLY, box, api, pending)
    assert api.booked == ["R-1"]  # the backend books its pending rate for this call: one portal booking
    box, api = FixtureMailbox(tmp_path), FakeApi([{**pending, "stage": "quoted"}])
    handle_tracking({"id": 140, "thread_id": 140, "from": "tracking@hackloop.mail", "subject": "Status",
                     "body": "Where is my shipment for PO-4711?"}, box, api)
    assert "starts with BK-" in box.sent[0]["body"]  # asks for the reference instead of crashing


def test_tracking_question_without_reference_is_matched_by_the_shipment(tmp_path):
    sonnberg = {**SESSION, "id": 2, "customer": "sonnberg-roesterei@hackloop.mail", "stage": "booked",
                "rfq": {"origin": "FRA", "destination": "JFK", "ready_date": "2026-11-25",
                        "pickup": {"address": "61018 (Bad Homburg), Germany", "zone": None},
                        "pieces": [{"count": 6, "weight_kg": 205.5}]},
                "booking": {**BOOKING, "booking_reference": "BK-URPNYJ4M", "status": "confirmed"}}
    auer = {**SESSION, "id": 3, "customer": "auer-maschinenbau@hackloop.mail", "stage": "booked",
            "rfq": {"origin": "DUS", "destination": "JFK", "ready_date": "2026-11-26", "pickup": None,
                    "pieces": [{"count": 2, "weight_kg": 300}]},
            "booking": {**BOOKING, "booking_reference": "BK-UHRIJQ2L", "status": "confirmed"}}
    box, api = FixtureMailbox(tmp_path), FakeApi([sonnberg, auer])
    mail = {"id": 923, "thread_id": 923, "from": "tracking@hackloop.mail",
            "subject": "Status of our shipment 61018 to JFK, 1233 kg",
            "body": "could you please tell me the current status of our shipment: Sonnberg Kaffeeroesterei GmbH, "
                    "61018 to JFK, 1233 kg, ready on 2026-11-25? Where is it now?"}
    handle_tracking(mail, box, api)
    [answer] = box.sent
    assert "BK-URPNYJ4M" in answer["body"] and "2026-11-25" in answer["body"]
    assert api.events == ["tracking_answer"]


def test_a_customer_mail_on_a_handed_over_rfq_reaches_a_person(tmp_path):
    import amendments
    handed_over = {**SESSION, "stage": "pricing", "needs_human": True, "quote": None}
    api = FakeApi([handed_over])
    mail = {**REPLY, "body": "Sorry, the dimensions are 120 x 80 x 100 cm per pallet."}
    handle_customer_reply(mail, FixtureMailbox(tmp_path), api, handed_over)
    assert "needs_human" in api.events and amendments.take(mail["thread_id"]) == []
    pricing = {**SESSION, "stage": "pricing", "quote": None}  # still being priced: parked for the re-read
    handle_customer_reply(mail, FixtureMailbox(tmp_path), FakeApi([pricing]), pricing)
    assert len(amendments.take(mail["thread_id"])) == 1


class BookFailed(Exception):
    """What backend.Backend.book raises: an httpx error whose response carries /api/book's detail."""

    def __init__(self, detail):
        super().__init__("Server error '502 Bad Gateway' for url 'http://localhost:8000/api/book'")
        self.response = type("Response", (), {"text": f'{{"detail":"{detail}"}}'})()


class NoPortal(FakeApi):
    """The portal can't book the accepted option (round 16: Meridian was not on the portal for PVG)."""
    detail = ("None has no portal rate ID (manual option) and is not on the portal for this lane: "
              "book it by email with the airline")

    def book(self, session_id, rate_id):
        raise BookFailed(self.detail)


def test_a_quote_the_portal_cant_book_is_booked_by_email_with_the_airline(tmp_path):
    session = {**SESSION, "quote": {**SESSION["quote"], "carrier": "Meridian Freightways", "rate_id": None,
                                    "billed_weight_kg": 349.0},
               "rfq": {**SESSION["rfq"], "ready_date": "2026-12-02", "contact_name": "Mira Petersen"},
               "bids": [{"leg": "air", "carrier": "Meridian Freightways", "rate_id": "R-MER123", "total": 1400.0}]}
    box, api = FixtureMailbox(tmp_path), NoPortal([session])
    handle_customer_reply(REPLY, box, api, session)
    to_airline, to_customer = box.sent
    assert to_airline["to"] == "meridian-freightways@hackloop.mail" and "R-MER123" in to_airline["body"]
    assert "S-17" in to_airline["body"] and "349.00 kg" in to_airline["body"]
    assert to_customer["to"] == "buyer@customer.example" and to_customer["body"].startswith("Hi Mira,")
    assert api.sessions[17]["booking"]["pending_email"] == "meridian-freightways@hackloop.mail"
    assert api.sessions[17]["needs_human"] is True  # until the airline's confirmation is matched (phone push)
    assert "error" not in api.events and "needs_human" in api.events


class EmailBookingApi:
    def __init__(self, session):
        self.s, self.events = dict(session), []

    def find(self, thread_id=None, reference=None):
        return None  # the portal never issued this BK- reference to us

    def sessions(self):
        return [self.s]

    def update(self, session_id, **fields):
        self.s.update(fields)

    def event(self, session_id, kind, text, data=None, cost=0.0):
        self.events.append(kind)


def test_the_airlines_confirmation_completes_an_email_booking(tmp_path):
    pending = {**SESSION, "stage": "booked", "booking": {"pending_email": "meridian-freightways@hackloop.mail",
                                                          "airline": "Meridian Freightways", "rate_id": "R-MER123"}}
    api, box = EmailBookingApi(pending), FixtureMailbox(tmp_path)
    confirmation = {"id": 900, "thread_id": 900, "from": "Meridian-Freightways@hackloop.mail",
                    "subject": "Booking BK-ABCD1234 confirmed", "body": "Booking BK-ABCD1234 confirmed."}
    assert handle_booking_confirmed(confirmation, box, api)
    assert api.s["booking"]["booking_reference"] == "BK-ABCD1234" and api.s["booking"]["status"] == "confirmed"
    assert api.s["needs_human"] is False and api.s["booking"]["rate_id"] == "R-MER123"  # merged, not replaced
    assert box.sent[-1]["to"] == "buyer@customer.example" and "status_sent" in api.events


def test_email_booking_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(booking_agent, "EMAIL_BOOKING", False)
    session = {**SESSION, "quote": {**SESSION["quote"], "carrier": "Meridian Freightways", "rate_id": None}}
    box, api = FixtureMailbox(tmp_path), NoPortal([session])
    handle_customer_reply(REPLY, box, api, session)
    assert box.sent == [] and "error" in api.events  # as before: the session shows the failure for a person


def test_a_portal_timeout_never_books_by_email(tmp_path):
    class Timeout(NoPortal):
        detail = "portal unreachable: ReadTimeout"  # it may have booked: mailing the airline could book twice

    session = {**SESSION, "quote": {**SESSION["quote"], "carrier": "Meridian Freightways", "rate_id": None}}
    box, api = FixtureMailbox(tmp_path), Timeout([session])
    handle_customer_reply(REPLY, box, api, session)
    assert box.sent == [] and "error" in api.events and not api.sessions[17].get("booking")


def test_no_email_booking_when_the_portal_booked_after_all(tmp_path):
    session = {**SESSION, "quote": {**SESSION["quote"], "carrier": "Meridian Freightways", "rate_id": None}}

    class BookedMeanwhile(NoPortal):
        def book(self, session_id, rate_id):
            self.sessions[session_id]["booking"] = BOOKING  # the portal booked, but its answer came back as an error
            super().book(session_id, rate_id)

    box, api = FixtureMailbox(tmp_path), BookedMeanwhile([session])
    handle_customer_reply(REPLY, box, api, session)
    [to_customer] = box.sent  # the normal booking mail, no mail to the airline
    assert to_customer["to"] == "buyer@customer.example" and BOOKING["booking_reference"] in to_customer["body"]


def test_an_email_booking_keeps_what_the_booking_record_already_holds(tmp_path):
    session = {**SESSION, "quote": {**SESSION["quote"], "carrier": "Meridian Freightways", "rate_id": "R-MER9"},
               "booking": {"note": "kept"}}
    box, api = FixtureMailbox(tmp_path), NoPortal([session])
    handle_customer_reply(REPLY, box, api, session)
    assert api.sessions[17]["booking"]["note"] == "kept" and api.sessions[17]["booking"]["rate_id"] == "R-MER9"


def test_an_email_booking_confirmation_from_a_named_sender_is_matched(tmp_path):
    pending = {**SESSION, "stage": "booked",
               "booking": {"pending_email": "meridian-freightways@hackloop.mail", "airline": "Meridian Freightways"}}
    api = EmailBookingApi(pending)
    handle_booking_confirmed({"id": 1, "thread_id": 1, "from": "Meridian Freightways <meridian-freightways@hackloop.mail>",
                              "subject": "Booking BK-ABCD1234 confirmed", "body": ""}, FixtureMailbox(tmp_path), api)
    assert api.s["booking"].get("booking_reference") == "BK-ABCD1234"


def test_a_backend_blip_never_mails_the_airline_twice(tmp_path):
    class Flaky(NoPortal):
        fail = True

        def update(self, sid, **fields):
            if self.fail and (fields.get("booking") or {}).get("pending_email"):
                self.fail = False
                raise RuntimeError("backend blip")
            return super().update(sid, **fields)

    session = {**SESSION, "quote": {**SESSION["quote"], "carrier": "Meridian Freightways", "rate_id": None}}
    api, box = Flaky([session]), FixtureMailbox(tmp_path)
    handle_customer_reply(REPLY, box, api, api.sessions[17])
    handle_customer_reply(REPLY, box, api, api.sessions[17])
    assert sum(m["to"].startswith("meridian") for m in box.sent) == 1  # bookings are public and can't be cancelled


def test_a_rejection_notice_is_a_free_decline_and_a_plain_yes_still_books(monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no LLM")))
    for body in ("Thank you for your offer, but your price is too high for us, so we will not go ahead with it.",
                 "That seems too low to be right, so we will not go ahead with it.",
                 "Thanks, but we won't book this one."):
        assert read_intent(body) == ("decline", 0.0), body
    for body in ("That works for us, please go ahead and book it.", "Yes please, go ahead."):
        assert read_intent(body) == ("accept", 0.0), body


def test_cannot_wait_and_do_not_hesitate_are_a_yes_and_a_real_refusal_is_a_no(monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a, **k: ({"intent": "accept"}, 0.00004))
    for body in ("We cannot wait to book this, please proceed.", "Please do not hesitate to book it for us.",
                 "Please proceed."):
        assert read_intent(body)[0] == "accept", body
    assert read_intent("We will not proceed with this offer.") == ("decline", 0.0)
    assert read_intent("We cannot accept this price.") == ("decline", 0.0)



def test_a_promise_to_send_the_dg_papers_is_answered_not_handed_over(tmp_path, monkeypatch):
    """R39: 'We will send you the dangerous goods documents shortly.' went to a person."""
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "other"}, 0.00003))
    box, api = FixtureMailbox(tmp_path), FakeApi([SESSION])
    mail = {**REPLY, "body": "Thank you, good point. We will send you the dangerous goods documents (shipper's "
                             "declaration and safety data sheet) shortly.\n\nKind regards\nAnna Sonnberg"}
    handle_customer_reply(mail, box, api, SESSION)
    assert api.booked == [] and "needs_human" not in api.events and api.events[-1] == "routed"
    [sent] = box.sent
    assert "EUR 1,856.00" in sent["body"] and "SkyAir" in sent["body"] and api.sessions[17]["stage"] == "quoted"
    # a question about the papers still goes to a person, and so does the switch off
    box2, api2 = FixtureMailbox(tmp_path / "2"), FakeApi([SESSION])
    handle_customer_reply({**mail, "body": "Which documents will you need from us?"}, box2, api2, SESSION)
    assert "needs_human" in api2.events and box2.sent == []
    monkeypatch.setattr(booking_agent, "DOCS_ACK", False)
    box3, api3 = FixtureMailbox(tmp_path / "3"), FakeApi([SESSION])
    handle_customer_reply(mail, box3, api3, SESSION)
    assert "needs_human" in api3.events and box3.sent == []



def test_hold_off_on_booking_is_never_a_yes(monkeypatch):
    """R39: 'Please hold off on booking for now.' was booked."""
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "accept"}, 0.00003))
    r39 = ("Dear Lena,\n\nThank you. I will check on the Shipper's Declaration for Dangerous Goods and the safety "
           "data sheet and get back to you. Please hold off on booking for now.\n\nKind regards\nAnna")
    assert read_intent(r39)[0] == "wait"
    assert read_intent("Not yet please, we'll confirm the booking tomorrow.")[0] == "wait"
    assert read_intent("Bitte noch nicht buchen.")[0] != "accept"
    assert read_intent("Yes please, go ahead.\n\nOn Sat, team wrote:\n> wait")[0] == "accept"  # quoted text ignored
    assert read_intent("Great, can't wait, please book it.")[0] == "accept"



def test_a_clear_yes_with_a_later_note_still_books(monkeypatch):
    """Review of the R39 fix: only booking-stopping phrases hold, a yes plus 'later' / 'let you know' books."""
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "question"}, 0.00003))
    assert read_intent("Yes, please book it. The DG documents will follow later.")[0] == "accept"
    assert read_intent("Great, go ahead and book. I will let you know the exact pickup time.")[0] == "accept"
    assert read_intent("Please hold off on booking for now.")[0] == "wait"



def test_wait_replies_keep_the_quote_open_and_the_dg_papers_book(tmp_path, monkeypatch):
    """Review: 'do not book yet' closed the quote as lost. R40: 'I'll check and get back to you' went to a person."""
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "decline"}, 0.00003))
    for text in ("Please do not book yet.", "Don't book it yet please.", "Bitte noch nicht buchen.",
                 "Please hold off on booking for now."):
        assert read_intent(text)[0] == "wait", text
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a: ({"intent": "other"}, 0.00003))
    box, api = FixtureMailbox(tmp_path), FakeApi([SESSION])
    later = {**REPLY, "body": "Thanks. I'll check on the Shipper's Declaration and the safety data sheet and get back to you."}
    handle_customer_reply(later, box, api, SESSION)
    assert box.sent == [] and "needs_human" not in api.events and api.sessions[17]["stage"] == "quoted"
    dg = {**SESSION, "rfq": {**SESSION["rfq"], "dangerous_goods": True}}
    box2, api2 = FixtureMailbox(tmp_path / "2"), FakeApi([dg])
    papers = {**REPLY, "body": "Hi Lena, please find attached the shipper's declaration and the safety data sheet.",
              "attachments": [{"id": 1, "filename": "DGD.pdf"}]}
    handle_customer_reply(papers, box2, api2, dg)
    assert api2.booked == ["R-1"] and api2.sessions[17]["stage"] == "booked"
    box3, api3 = FixtureMailbox(tmp_path / "3"), FakeApi([dg])  # papers, but "hold off": no booking
    handle_customer_reply({**papers, "body": papers["body"] + " Please hold off on booking for now."}, box3, api3, dg)
    assert api3.booked == []
    monkeypatch.setattr(booking_agent, "DOCS_BOOK", False)
    box4, api4 = FixtureMailbox(tmp_path / "4"), FakeApi([dg])
    handle_customer_reply(papers, box4, api4, dg)
    assert api4.booked == []



def _fake_llm(intent, topic):
    return lambda name, *a: ({"intent": intent} if name == "intent" else {"topic": topic}, 0.00003)


def test_questions_the_quote_answers_are_answered_others_go_to_a_person(tmp_path, monkeypatch):
    """R41: 'Could you please send your quote for the most economical option to SGN before reserving space?'"""
    monkeypatch.setattr(booking_agent.llm, "chat_json", _fake_llm("question", "quote_again"))
    session = {**SESSION, "rfq": {**SESSION["rfq"], "ready_date": "2026-11-23", "contact_name": "Anna Sonnberg"}}
    box, api = FixtureMailbox(tmp_path), FakeApi([session])
    r41 = {**REPLY, "body": "Hi Lena,\n\nThank you for the update. Could you please send your quote for the most "
                            "economical option to SGN before reserving space?\n\nKind regards\nAnna Sonnberg"}
    handle_customer_reply(r41, box, api, session)
    [sent] = box.sent
    assert "EUR 1,856.00" in sent["body"] and "SkyAir" in sent["body"] and "New York (JFK)" in sent["body"]
    assert api.booked == [] and "needs_human" not in api.events and api.sessions[17]["rfq"]["auto_answers"] == 1
    # customs is not in the quote: a person; a discount request never reaches the model
    monkeypatch.setattr(booking_agent.llm, "chat_json", _fake_llm("question", "other"))
    box2, api2 = FixtureMailbox(tmp_path / "2"), FakeApi([session])
    handle_customer_reply({**r41, "body": "Can you also handle the customs clearance in Vietnam?"}, box2, api2, session)
    assert box2.sent == [] and "needs_human" in api2.events
    monkeypatch.setattr(booking_agent.llm, "chat_json", _fake_llm("question", "quote_again"))
    box3, api3 = FixtureMailbox(tmp_path / "3"), FakeApi([session])
    handle_customer_reply({**r41, "body": "Could you do it 10% cheaper?"}, box3, api3, session)
    assert box3.sent == [] and "needs_human" in api3.events
    many = {**session, "rfq": {**session["rfq"], "auto_answers": 2}}  # after two automatic answers, a person
    box4, api4 = FixtureMailbox(tmp_path / "4"), FakeApi([many])
    handle_customer_reply(r41, box4, api4, many)
    assert box4.sent == [] and "needs_human" in api4.events



def test_change_requests_never_get_the_old_quote_again(tmp_path, monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", _fake_llm("question", "quote_again"))
    for text in ("Could you send a revised quote for 3 pallets instead of 2?",
                 "Please send the quote again, but for delivery to Munich.",
                 "Could you send an offer for express service as well?",
                 "What would the price be without the pickup?",
                 "Can you confirm the price is valid until Friday?"):
        box, api = FixtureMailbox(tmp_path / str(abs(hash(text)))), FakeApi([SESSION])
        handle_customer_reply({**REPLY, "body": text}, box, api, SESSION)
        assert box.sent == [] and "needs_human" in api.events, text



def test_the_dg_ack_says_we_book_when_the_papers_arrive():
    """Review: the ack said 'won't book until you confirm' while DOCS_BOOK books on the papers."""
    from templates import docs_ack_text
    dg = docs_ack_text({"origin": "STR", "destination": "MIA", "dangerous_goods": True, "language": "en"},
                       {"carrier": "Solace Air Cargo", "currency": "EUR", "total": 1172.84})
    assert "as soon as the Shipper's Declaration" in dg and "unless you tell me to wait" in dg and "won't book" not in dg
    plain = docs_ack_text({"origin": "STR", "destination": "MIA", "language": "en"}, {})
    assert "won't book anything until you confirm" in plain



def test_a_change_request_is_never_answered_with_the_old_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(booking_agent.llm, "chat_json", lambda *a, **k: ({"intent": "question"}, 0.00003))
    for body in ("Could you send a revised quote for 3 pallets instead of 2?", "Please quote again but for delivery to Munich.",
                 "Could you send me the price without the pickup?"):
        box, api = FixtureMailbox(tmp_path / str(abs(hash(body)))), FakeApi([SESSION])
        handle_customer_reply({**REPLY, "body": body}, box, api, SESSION)
        assert box.sent == [] and "needs_human" in api.events, body
