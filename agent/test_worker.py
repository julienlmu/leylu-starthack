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

    def dispatch(mail, box, api, board, carriers):
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
    def dispatch(mail, box, api, board, carriers):
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
