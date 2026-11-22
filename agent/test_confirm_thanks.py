"""CONFIRM_THANKS: the airline's confirmation mail ends with one short, varied thank-you (first name where we have it);
quotes and every other mail are unchanged, and the line carries no number."""
import re

import pytest

import short_mail

@pytest.fixture(autouse=True)
def between(monkeypatch):
    import quote_style
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "between")  # the live default (conftest sets classic)


BOOKING = {"airline": "Nova Atlas Cargo", "booking_reference": "BK-9MIY9ZX8"}


def mail(lang="en", name="Jonas Berg", formal=None, ref="BK-9MIY9ZX8"):
    return short_mail.confirmed({"rfq": {"language": lang, "contact_name": name, "formal": formal},
                                 "booking": {**BOOKING, "booking_reference": ref}})


def test_english_thanks_by_first_name():
    text = mail()
    assert "BK-9MIY9ZX8" in text and "Nova Atlas Cargo" in text
    assert re.search(r"Thanks Jonas, (pleasure|it was a pleasure|great) working|Thanks Jonas, it was a pleasure", text)


def test_varied_per_booking_and_no_corporate_line():
    texts = {mail(ref=f"BK-{i}") for i in range(12)}
    lines = {re.search(r"Thanks Jonas[^.\n]*", t).group(0) for t in texts}
    assert len(lines) >= 2
    assert all("choosing" not in t and "business" not in t for t in texts)


def test_no_new_number_in_the_mail():
    off = short_mail.CONFIRM_THANKS
    with_line = mail()
    short_mail.CONFIRM_THANKS = False
    try:
        without = mail()
    finally:
        short_mail.CONFIRM_THANKS = off
    assert re.findall(r"\d", with_line) == re.findall(r"\d", without) and with_line != without


def test_german_formal_has_no_first_name():
    assert "Danke Jonas" in mail("de") or "Jonas, die" in mail("de")
    formal = mail("de", formal=True)
    assert "Danke Jonas" not in formal and ("Vielen Dank" in formal or "Herzlichen Dank" in formal)


def test_no_name_no_name():
    assert "Thanks," in mail(name=None)


def test_other_languages_and_switch_off_unchanged(monkeypatch):
    fr = mail("fr")
    assert "Thanks" not in fr.split("\n\n")[1] and "Merci" not in fr.split("\n\n")[1], fr
    monkeypatch.setattr(short_mail, "CONFIRM_THANKS", False)
    assert "Thanks Jonas" not in mail() and "pleasure" not in mail()


def test_formal_english_and_titles_get_no_name():
    formal = mail(formal=True)
    assert "Thanks Jonas" not in formal and "Best regards" in formal and "Thanks," in formal
    for name in ("Ms Anna Weber", "Dr. Klaus Meyer"):
        text = mail(name=name)
        assert "Thanks Ms" not in text and "Thanks Dr" not in text and "Thanks," in text


def test_short_style_unchanged(monkeypatch):
    import quote_style
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "short")
    with_line = mail()
    monkeypatch.setattr(short_mail, "CONFIRM_THANKS", False)
    assert with_line == mail()  # its sign-off already says "Thanks,"
