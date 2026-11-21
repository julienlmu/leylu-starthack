

import pytest


@pytest.fixture(autouse=True)
def _classic_quote_style(monkeypatch):
    """Live default is the humanizer (style "a"); tests pin the classic wording unless they set a style themselves."""
    import quote_style
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "classic")


@pytest.fixture(autouse=True)
def _no_reply_translation(monkeypatch):
    """The reply-language guard may call the gateway: off in tests unless a test turns it on (test_language.py)."""
    import language
    monkeypatch.setattr(language, "REPLY_LANGUAGE", False)
