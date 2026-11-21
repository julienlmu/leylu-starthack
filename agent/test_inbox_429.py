import httpx
import pytest

import inbox


def mailbox(tmp_path, handler):
    box = inbox.FiveUMailbox(key="k", state_file=str(tmp_path / "since"))
    box.http = httpx.Client(base_url="http://5u.test", transport=httpx.MockTransport(handler))
    return box


def test_a_429_waits_and_retries_so_nothing_is_lost(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if len(calls) == 1:
            return httpx.Response(429, json={"detail": "one poll per 5 seconds", "retry_after": 1})
        return httpx.Response(200, content=b"PDF")

    monkeypatch.setattr(inbox.time, "sleep", lambda s: calls.append(f"sleep {s}"))
    assert mailbox(tmp_path, handler).attachment({"id": 7}, {"id": 3}) == b"PDF"
    assert calls[1] == "sleep 1.0" and len(calls) == 3


def test_a_429_that_never_ends_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox.time, "sleep", lambda s: None)
    box = mailbox(tmp_path, lambda r: httpx.Response(429, json={"retry_after": 0}))
    with pytest.raises(httpx.HTTPStatusError):
        box.fetch()
