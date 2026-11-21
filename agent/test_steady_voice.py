"""Our voice never copies the sender's (Julien, 22 Nov): formal, casual, slang, shouting, emoji, rude or broken
English, the same request gets the same reply, word for word. Live style (QUOTE_STYLE=short), whole RFQ path."""
import pytest

import extract as extract_mod
import quote_style
import rfq_agent
from inbox import FixtureMailbox
from test_rfq_agent import FakeApi, OPTION, RAW

ASK = "2 crates MUC to JFK, 48 x 40 x 40 in, 440 lb total, pickup Industriestr. 12, 85748 Garching, ready 2026-11-23."
STYLES = [
    f"Dear Sir or Madam,\n\nWe would be most grateful for your quotation: {ASK}\n\nYours faithfully,\nAnna Meyer",
    f"Hi Lena!!\n\nHope your week's going great :) {ASK} Thanks a ton!!\n\nCheers,\nAnna Meyer",
    f"yo, need a price asap lol. {ASK} thx\n\nCheers\nAnna Meyer",
    f"HELLO. I NEED A QUOTE NOW. {ASK.upper()} DO NOT WASTE MY TIME.\n\nRegards\nAnna Meyer",
    f"Hey 👋🚀 {ASK} 🙏🙏 ✈️📦\n\nBest,\nAnna Meyer",
    f"Your last quote was a joke. Do better this time. {ASK}\n\nRegards,\nAnna Meyer",
    f"hello sir, kindly do the needful and revert back with best rate. {ASK} pls do fast\n\nThanks & Regards\nAnna Meyer",
    f"{ASK}\n\nthx\nAnna Meyer",
    f"Good morning,\n\nI trust this message finds you well. Further to our telephone conversation, {ASK} "
    f"I look forward to hearing from you at your earliest convenience.\n\nWith kind regards,\nAnna Meyer",
    f"Hi,\n\nsry for typos, on my phone. {ASK} ty\n\nKind regards\nAnna Meyer",
]

ASK_DE = "2 Kisten MUC nach JFK, 48 x 40 x 40 in, 440 lb gesamt, Abholung Industriestr. 12, 85748 Garching, bereit 2026-11-23."
STYLES_DE = [
    f"Sehr geehrte Damen und Herren,\n\nbitte senden Sie uns Ihr Angebot: {ASK_DE}\n\nMit freundlichen Grüßen\nAnna Meyer",
    f"Guten Tag Frau Hartmann,\n\nkönnten Sie uns bitte ein Angebot machen? {ASK_DE}\n\nFreundliche Grüße\nAnna Meyer",
    f"Hallo Lena,\n\nkannst du mir schnell einen Preis schicken? {ASK_DE} Danke dir!\n\nViele Grüße\nAnna Meyer",
    f"hey lena, brauch nen preis, eilt. {ASK_DE} thx euch\n\nGruß\nAnna Meyer",
]


@pytest.fixture(autouse=True)
def _live_style(monkeypatch):
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "short")


def _reply(body, tmp_path, monkeypatch, n):
    monkeypatch.setattr(extract_mod, "extract", lambda mail, model=None: (RAW, 0.0001))
    box, api = FixtureMailbox(tmp_path / str(n)), FakeApi({"options": [OPTION], "chosen": OPTION, "why": "cheapest"})
    rfq_agent.handle_rfq({"id": f"m{n}", "thread_id": f"t{n}", "from": "anna@meyer.example", "subject": "RFQ",
                          "body": body}, box, api)
    [sent] = box.sent
    return sent["body"]


def test_the_quote_is_the_same_whatever_the_senders_style(tmp_path, monkeypatch):
    replies = [_reply(body, tmp_path, monkeypatch, n) for n, body in enumerate(STYLES)]
    assert len(set(replies)) == 1, "\n---\n".join(dict.fromkeys(replies))
    text = replies[0]
    assert text.startswith("Hallo Anna,") and "lol" not in text and "!!" not in text and "needful" not in text


def test_german_sie_and_du_senders_get_the_same_quote_in_our_sie_voice(tmp_path, monkeypatch):
    replies = [_reply(body, tmp_path, monkeypatch, n) for n, body in enumerate(STYLES_DE)]
    assert len(set(replies)) == 1, "\n---\n".join(dict.fromkeys(replies))
    text = replies[0]
    assert text.startswith("Hallo Anna,") and "Guten Tag" not in text and "dir" not in text.split()


def test_the_answer_to_a_question_about_the_quote_is_the_same_too():
    rfq = {"contact_name": "Anna Meyer", "language": "en", "origin": "MUC", "destination": "JFK", "ask": "cheapest",
           "pieces": [{"count": 2, "weight_kg": 100}], "ready_date": "2026-11-23", "pickup": None}
    quote = {**OPTION, "pickup": None}
    answers = {quote_style.quote_summary_text(rfq, quote, body) for body in STYLES}
    assert len(answers) == 1 and next(iter(answers)).startswith("Hi Anna,")
