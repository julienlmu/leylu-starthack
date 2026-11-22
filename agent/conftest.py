

import pytest


@pytest.fixture(autouse=True)
def _classic_quote_style(monkeypatch):
    """Live default is the humanizer (style "a"); tests pin the classic wording unless they set a style themselves."""
    import quote_style
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "classic")


@pytest.fixture(autouse=True)
def _no_web(request, monkeypatch):
    """Tests never open a real link: links found in a test mail resolve to nothing (test_links uses a fake web)."""
    import links
    if request.module.__name__ != "test_links":
        monkeypatch.setattr(links, "_public", lambda host, resolve=None: False)


@pytest.fixture(autouse=True)
def _no_book_grace(monkeypatch):
    """BOOK_GRACE_S waits 25 s before a booking in production; tests book at once (test_night_traps checks the wait)."""
    import booking_agent
    monkeypatch.setattr(booking_agent, "BOOK_GRACE_S", 0)
