"""Steady voice, Ulas's "in-between" style (QUOTE_STYLE=between, docs/HUMAN_MAILS.md; Julien 22 Nov 01:30): every
sender gets the same facts and the same one amount. Only greeting, closing and the small-talk line follow the sender:
formal ("Dear Sir or Madam", "kind regards") → "Hello Anna Meyer," … "best regards,"; everyone else → "Hi Anna," …
"cheers,". Slang, ALL CAPS, emoji and rudeness are never copied; German stays "Sie". Whole RFQ path."""
import pytest

import extract as extract_mod
import gate
import quote_style
import rfq_agent
from inbox import FixtureMailbox
from test_rfq_agent import FakeApi, OPTION, RAW

ASK = "2 crates MUC to JFK, 48 x 40 x 40 in, 440 lb total, pickup Industriestr. 12, 85748 Garching, ready 2026-11-23."
FORMAL = [
    f"Dear Sir or Madam,\n\nWe would be most grateful for your quotation: {ASK}\n\nYours faithfully,\nAnna Meyer",
    f"Good morning,\n\nI trust this message finds you well. Further to our telephone conversation, {ASK} "
    f"I look forward to hearing from you at your earliest convenience.\n\nWith kind regards,\nAnna Meyer",
]
CHAT = f"Hi Lena!!\n\nHope your week's going great :) {ASK} Thanks a ton!!\n\nCheers,\nAnna Meyer"
CASUAL = [
    f"yo, need a price lol. {ASK} thx\n\nCheers\nAnna Meyer",
    f"HELLO. I NEED A QUOTE. {ASK.upper()} DO NOT WASTE MY TIME.\n\nRegards\nAnna Meyer",
    f"Hey 👋🚀 {ASK} 🙏🙏 ✈️📦\n\nBest,\nAnna Meyer",
    f"Your last quote was a joke. Do better this time. {ASK}\n\nRegards,\nAnna Meyer",
    f"hello sir, kindly do the needful and revert back with best rate. {ASK} pls\n\nThanks & Regards\nAnna Meyer",
    f"{ASK}\n\nthx\nAnna Meyer",
]
COPIED = ["lol", "!!", "needful", "yo,", "thx", "👋", "🙏", "JOKE", "WASTE", "HELLO.", "pls", "revert"]

ASK_DE = "2 Kisten MUC nach JFK, 48 x 40 x 40 in, 440 lb gesamt, Abholung Industriestr. 12, 85748 Garching, bereit 2026-11-23."
FORMAL_DE = [
    f"Sehr geehrte Damen und Herren,\n\nbitte senden Sie uns Ihr Angebot: {ASK_DE}\n\nMit freundlichen Grüßen\nAnna Meyer",
    f"Guten Tag Frau Hartmann,\n\nkönnten Sie uns bitte ein Angebot machen? {ASK_DE}\n\nFreundliche Grüße\nAnna Meyer",
]
CASUAL_DE = [
    f"Hallo Lena,\n\nkannst du mir schnell einen Preis schicken? {ASK_DE} Danke dir!\n\nViele Grüße\nAnna Meyer",
    f"hey lena, brauch nen preis, eilt. {ASK_DE} thx euch\n\nGruß\nAnna Meyer",
]


@pytest.fixture(autouse=True)
def _live_style(monkeypatch):
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "between")


def _reply(body, tmp_path, monkeypatch, n, lang):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: ({**RAW, "language": lang}, 0.0001))
    box, api = FixtureMailbox(tmp_path / str(n)), FakeApi({"options": [OPTION], "chosen": OPTION, "why": "cheapest"})
    rfq_agent.handle_rfq({"id": f"m{n}", "thread_id": f"t{n}", "from": "anna@meyer.example", "subject": "RFQ",
                          "body": body}, box, api)
    [sent] = box.sent
    return sent["body"]


def _facts_hold(text):
    assert gate.MONEY.findall(text) == ["1,856.00"] and "EUR 1,856.00" in text, text
    assert "SkyAir" in text and "MUC" in text and "JFK" in text and "PO-4711" in text, text
    assert "2026-11-23" not in text and "23.11." not in text, text


def test_english_formal_and_casual_senders_get_the_same_offer_in_their_register(tmp_path, monkeypatch):
    replies = {body: _reply(body, tmp_path, monkeypatch, n, "en") for n, body in enumerate(FORMAL + [CHAT] + CASUAL)}
    for body, text in replies.items():
        _facts_hold(text)
        assert "your 2 crates of machine parts" in text and "in Garching included" in text, text
        assert not any(word in text for word in COPIED), text
        if body in FORMAL:
            assert text.startswith("Hello Anna Meyer,\n\nThank you for your request.") and text.endswith("Best regards,\nLena")
        else:
            assert text.startswith("Hi Anna,") and text.endswith("Cheers,\nLena"), text
    assert "All good here thanks and I hope yours is too!" in replies[CHAT]  # small talk answered once
    assert sum("hope yours is too" in text for text in replies.values()) == 1
    # same register, no small talk: word for word the same mail, whatever their slang, shouting or emoji
    plain = {text for body, text in replies.items() if body in CASUAL and "fastest" not in text}
    assert len(plain) == 1, "\n---\n".join(plain)
    assert len({text for body, text in replies.items() if body in FORMAL}) == 1


def test_a_title_only_when_the_customer_wrote_it(tmp_path, monkeypatch):
    text = _reply(f"Dear Sir or Madam,\n\n{ASK}\n\nKind regards,\nMs Anna Meyer", tmp_path, monkeypatch, 0, "en")
    assert text.startswith("Hello Ms Meyer,")


def test_german_sie_always_formal_or_not(tmp_path, monkeypatch):
    replies = {body: _reply(body, tmp_path, monkeypatch, n, "de") for n, body in enumerate(FORMAL_DE + CASUAL_DE)}
    for body, text in replies.items():
        _facts_hold(text)
        assert "Ihre 2 Kisten Maschinenteile" in text or "Ihre 2 Kisten machine parts" in text, text
        assert not {"du", "dir", "dein", "deine", "deinen", "dich"} & set(text.replace(",", " ").split()), text
        assert "nen" not in text.split() and "thx" not in text
        if body in FORMAL_DE:
            assert text.startswith("Guten Tag Anna Meyer,") and text.endswith("Freundliche Grüße\nLena"), text
        else:
            assert text.startswith("Hallo Anna,") and text.endswith("Viele Grüße\nLena"), text


def test_the_answer_to_a_question_about_the_quote_is_the_same_too():
    rfq = {"contact_name": "Anna Meyer", "language": "en", "origin": "MUC", "destination": "JFK", "ask": "cheapest",
           "pieces": [{"count": 2, "weight_kg": 100}], "ready_date": "2026-11-23", "pickup": None}
    quote = {**OPTION, "pickup": None}
    answers = {quote_style.quote_summary_text(rfq, quote, body) for body in FORMAL + CASUAL}
    assert len(answers) == 1 and next(iter(answers)).startswith("Hi Anna,")
