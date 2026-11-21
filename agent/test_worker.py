import httpx

import llm
import main

MAIL = {"id": 7, "thread_id": 7, "from": "buyer@customer.example", "subject": "RFQ", "body": "…"}


class Box:
    def __init__(self, *mails):
        self.mails = list(mails)

    def fetch(self):
        mails, self.mails = self.mails, []
        return mails


def test_a_mail_whose_dispatch_fails_is_retried_on_the_next_poll(monkeypatch):
    calls = []

    def dispatch(mail, *args):
        calls.append(mail["id"])
        if len(calls) == 1:
            raise httpx.ConnectError("backend restarting")

    monkeypatch.setattr(main, "dispatch", dispatch)
    box, failed = Box(MAIL), {}
    main.poll_once(box, None, None, [], failed)  # backend down: the mail is kept
    assert calls == [7] and 7 in failed
    main.poll_once(box, None, None, [], failed)  # backend back: dispatched, then forgotten
    assert calls == [7, 7] and failed == {}


def test_a_failing_mail_is_given_up_once_the_rfq_window_is_over(monkeypatch):
    def dispatch(mail, *args):
        raise httpx.ConnectError("backend down")

    monkeypatch.setattr(main, "dispatch", dispatch)
    monkeypatch.setattr(main.time, "time", lambda: 1000.0 + main.RETRY_SECONDS + 1)
    failed = {7: (MAIL, 1000.0)}  # it first failed at t=1000
    main.poll_once(Box(), None, None, [], failed)
    assert failed == {}


def test_gateway_calls_give_up_long_before_the_rfq_expires(monkeypatch):
    monkeypatch.setenv("FIVEU_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_client", None)
    client = llm.client()
    assert client.timeout == 20 and client.max_retries == 1


def test_a_second_worker_on_the_same_machine_refuses_to_start(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setenv("WORKER_LOCK_FILE", str(tmp_path / "worker.lock"))
    first = main.single_worker_lock()
    with pytest.raises(SystemExit):
        main.single_worker_lock()
    first.close()  # the first worker stops (or dies): the next one may start
    main.single_worker_lock().close()


def test_live_worker_skips_rfqs_that_already_expired(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from bids import BidBoard

    started = []
    monkeypatch.setattr(main, "_start", lambda handler, *args: started.append(args[0]["id"]))
    api = type("Api", (), {"find": lambda self, thread_id: None})()
    now = datetime.now(timezone.utc)
    old = {**MAIL, "id": 1, "thread_id": 1, "received_at": (now - timedelta(minutes=10)).isoformat()}
    fresh = {**MAIL, "id": 2, "thread_id": 2, "received_at": (now - timedelta(seconds=30)).isoformat()}
    for mail in (old, fresh):
        main.dispatch(mail, None, api, BidBoard(), [], main.RFQ_LIFETIME_SECONDS)
    assert started == [2]


def test_tariff_mails_in_every_start_kit_format_reach_the_backend_one_failure_doesnt_stop_the_rest():
    from router import route

    carriers = {"tariffs@quetzal.example"}
    for name in ("Quetzal_Dec.docx", "yellowtail.TXT", "Danube_p1.jpg", "Cobalt.xlsx"):
        mail = {"from": "tariffs@quetzal.example", "subject": "Tariff", "attachments": [{"filename": name}]}
        assert route(mail, carriers, known_thread=False) == "tariff", name

    class Box:
        def attachment(self, mail, attachment):
            return b"data"

    class Api:
        def __init__(self):
            self.ingested = []

        def ingest_tariff(self, filename, content, sender):
            if filename == "broken.pdf":
                raise httpx.HTTPStatusError("422", request=None, response=None)
            self.ingested.append(filename)
            return {"rows": 12}

    api = Api()
    mail = {"from": "tariffs@quetzal.example", "attachments": [{"filename": "broken.pdf"}, {"filename": "ok.xlsx"}]}
    main._forward_tariff(mail, Box(), api)
    assert api.ingested == ["ok.xlsx"]
