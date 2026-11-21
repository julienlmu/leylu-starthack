import httpx
import pytest

import inbox


def mailbox(tmp_path, handler):
    inbox.POLL_GAP_FILE = tmp_path / "poll-gap"  # shared by every process; per test here
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
        box.attachment({"id": 7}, {"id": 3})


def test_polls_are_never_less_than_5_seconds_apart_and_a_429_poll_is_not_retried(tmp_path, monkeypatch):
    """Round 48: a poll < 5 s after the last one costs 22.5 points."""
    clock, polls = [1000.0], []
    monkeypatch.setattr(inbox.time, "time", lambda: clock[0])
    monkeypatch.setattr(inbox.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))

    def handler(request):
        polls.append(clock[0])
        clock[0] += 0.8  # the response takes 0.8 s
        if len(polls) == 2:
            return httpx.Response(429, json={"retry_after": 1})
        return httpx.Response(200, json={"messages": [], "next_since_id": 0})

    box = mailbox(tmp_path, handler)
    box.fetch()
    with pytest.raises(httpx.HTTPStatusError):
        box.fetch()  # the 429 is not retried at once
    box.fetch()
    box.fetch()
    assert len(polls) == 4
    assert all(b - (a + 0.8) >= 5.5 for a, b in zip(polls, polls[1:]))  # end of one poll → start of the next
