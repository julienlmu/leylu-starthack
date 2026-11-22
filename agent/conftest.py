

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
def _no_portal_probe(request, monkeypatch):
    """PORTAL_PROBE prices once more in a background thread; the fake APIs hand out price results in order, so tests
    keep it off (test_portal_probe.py turns it on)."""
    import rfq_agent
    if request.module.__name__ != "test_portal_probe":
        monkeypatch.setattr(rfq_agent, "PORTAL_PROBE", False)
