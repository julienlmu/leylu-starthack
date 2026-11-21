"""R72 wrong_language: the customer's language read by code, and every reply (not just the quote) in it.

Main's one mechanism: rfq["language"] picks the template (16 native languages, others translated ONCE with placeholders
by short_mail._learn), code fills every fact, a finished mail never goes through a model.
"""

import json
import re
from datetime import date, timedelta

import pytest

import gate
import language
import quote_style
import short_mail
import templates
from booking_agent import booking_requested_text
from rfq_agent import details_question_text

R72 = ("您好，\n\n希望您这周过得顺利！想请您帮忙看看一票发往 LIM（Lima, PE）的空运。这票货我们想走最便宜的方案。\n\n"
       "货物是汽车传感器，共 11 件，毛重 704 kg，体积 3.08 cbm。2026-11-23 可以提货，提货地点是我们在 Cologne, Germany 的场地，"
       "邮编 50978。麻烦您安排卡车上门提货并送到机场。\n\n能否请您报一个包含上门提货和空运的 EUR 全包价？谢谢！\n\n"
       "Thanks a lot and have a lovely day!\nPetra Hofmann\nExport Desk, Hofmann Textilwerk KG")
SIG = "\n\nThanks a lot and have a lovely day!\nPetra Hofmann\nExport Desk, Hofmann Textilwerk KG"
OTHER = {
    "ar": "مرحباً،\nنرجو تزويدنا بأرخص عرض للشحن الجوي إلى LIM. الشحنة 11 قطعة، الوزن الإجمالي 704 كغ، جاهزة في 2026-11-23.",
    "ko": "안녕하세요,\n리마(LIM)행 항공 화물 견적을 부탁드립니다. 가장 저렴한 옵션으로 부탁드립니다. 총 11개, 704 kg입니다.",
    "ru": "Здравствуйте,\nпросим рассчитать самый дешёвый вариант авиаперевозки в LIM. 11 мест, брутто 704 кг.",
    "uk": "Добрий день,\nпрошу розрахувати найдешевший варіант авіадоставки до LIM. 11 місць, 704 кг. Дякуємо!",
    "ja": "お世話になっております。\nリマ（LIM）向けの航空貨物の見積もりをお願いいたします。最も安いオプションでお願いします。",
    "hi": "नमस्ते,\nकृपया LIM के लिए सबसे सस्ता एयर फ्रेट विकल्प बताएं। 11 पैकेज, 704 किलो।",
    "el": "Καλησπέρα σας,\nπαρακαλούμε για προσφορά αεροπορικής μεταφοράς προς LIM, την φθηνότερη επιλογή. 11 τεμάχια.",
    "he": "שלום,\nנבקש הצעת מחיר להובלה אווירית ל-LIM, האפשרות הזולה ביותר. 11 חבילות, 704 ק\"ג.",
    "th": "สวัสดีครับ\nขอใบเสนอราคาขนส่งทางอากาศไป LIM แบบถูกที่สุด 11 ชิ้น 704 กก.",
    "vi": "Xin chào,\nVui lòng báo giá vận chuyển hàng không rẻ nhất đến LIM. 11 kiện, 704 kg. Cảm ơn!",
    "tr": "Merhaba,\nLIM'e en ucuz hava kargo teklifini rica ediyoruz. 11 parça, 704 kg, Köln adresimizden alınabilir.",
    "pl": "Dzień dobry,\nproszę o najtańszą ofertę frachtu lotniczego do LIM. 11 sztuk, 704 kg, odbiór z Kolonii.",
    "hu": "Tisztelt Hölgyem/Uram!\nKérem a legolcsóbb légi fuvar ajánlatot LIM-be. 11 darab, 704 kg, Kölnben átvehető.",
    "ro": "Bună ziua,\nvă rog să ne trimiteți cea mai ieftină ofertă de transport aerian către LIM. 11 colete, 704 kg.",
    "nl": "Goedemiddag,\nkunt u ons de goedkoopste luchtvrachtoptie naar LIM aanbieden? Het gaat om 11 colli, 704 kg.",
    "pt": "Olá,\npoderia enviar a opção de frete aéreo mais barata para LIM? São 11 volumes, 704 kg, prontos em 2026-11-23.",
    "it": "Buongiorno,\npotreste inviarci l'opzione di trasporto aereo più economica per LIM? Si tratta di 11 colli, 704 kg.",
    "es": "Hola,\n¿podrían cotizar la opción de flete aéreo más barata a LIM? Son 11 bultos, 704 kg, listos el 2026-11-23.",
    "sv": "Hej,\nkan ni ge oss det billigaste flygfraktalternativet till LIM? Det gäller 11 kolli, 704 kg.",
    "da": "Hej,\nkan I give os den billigste luftfragtmulighed til LIM? Det drejer sig om 11 kolli, 704 kg, afhentning hos os.",
    "fr": "Bonjour,\nJ’espère que tout va bien de votre côté. J’ai un envoi de pièces détachées à faire partir vers Sydney.",
    "de": "Guten Tag,\nbitte bieten Sie uns die günstigste Luftfrachtoption nach RUH an. Die Sendung steht ab dem 2026-11-25 bei uns.",
}


def test_r72_chinese_with_an_english_closing_line_is_chinese():
    assert language.wanted({"subject": "空运询价：Cologne → LIM", "body": R72}) == "zh"


@pytest.mark.parametrize("code", sorted(OTHER))
def test_every_language_is_read_also_with_an_english_signature(code):
    for body in (OTHER[code], OTHER[code] + SIG):
        assert language.wanted({"subject": "Air freight LIM", "body": body}) == code


@pytest.mark.parametrize("body,code", [
    ("Guten Tag,\nbitte die günstigste Option nach LIM. 11 Stück, 704 kg. Bitte antworten Sie auf Englisch.", "en"),
    ("您好，想请您报一票发往LIM的空运，最便宜的方案。共11件，704 kg。请用英文回复，谢谢！", "en"),
    ("Hi, please quote the cheapest option to LIM, 11 pcs, 704 kg. Please reply in German, our Munich office handles it.",
     "de"),
    ("好的，请帮我们预订。", "zh"),
    ("Yes please, go ahead and book it.", "en"),
    ("Ja, bitte buchen Sie das so.", "de"),
    ("Hello,\nplease quote the cheapest option to LIM for 11 pieces, 704 kg.\n"
     "Pickup: Hofmann Textilwerk KG, Industriestraße 12, 50978 Köln, Deutschland\nThanks", "en"),
    ("Dear Sir or Madam / Sehr geehrte Damen und Herren,\nplease send us your best rate for 4 pallets, 900 kg to ORD, "
     "ready 2026-11-27, pickup from our site in Esslingen.\nMit freundlichen Grüßen / Kind regards", "en"),
])
def test_explicit_wishes_short_replies_and_addresses(body, code):
    assert language.wanted({"subject": "x", "body": body}) == code


def test_thanks_for_the_quote_is_no_signature():
    body = "Hi Lena,\n\nThanks for the quote, that works for us. Please go ahead and book it.\n\nBest regards\nAnna"
    assert "go ahead" in language.own_text(body)


# ---- every other mail in the customer's language: one amount at most, facts verbatim, no model call ----

NATIVE = ["en", "de", "fr", "es", "it", "nl", "pt", "tr", "pl", "cs", "sv", "da", "nb", "fi", "ja", "zh"]
READY = (date.today() + timedelta(days=3)).isoformat()
RFQ = {"origin": "MUC", "destination": "ORD", "pieces": [{"count": 3, "weight_kg": 213.4}], "contact_name": "Anna Berg",
       "dangerous_goods": False, "pickup": {"address": "Landsberger Str. 12, 80339 München"}, "ready_date": READY}
QUOTE = {"carrier": "Lumen Air Cargo", "currency": "EUR", "total": 2345.67, "transit_days": 3}
BOOKING = {"airline": "Lumen Air Cargo", "booking_reference": "BK-50NN8E8G", "status": "confirmed"}
BANNED = re.compile(r"hope this (email )?finds you|don'?t hesitate|zögern sie nicht|—|–", re.I)
ENGLISH = re.compile(r"\b(?:you|your|the|and|thanks|booked|shall)\b", re.I)
SDDG = "Shipper's Declaration for Dangerous Goods"


def _mails(lang: str, dg: bool) -> dict[str, str]:
    rfq = {**RFQ, "language": lang, "dangerous_goods": dg}
    session = {"rfq": rfq, "quote": QUOTE, "booking": BOOKING, "status_updates": []}
    other = {**session, "booking": {**BOOKING, "booking_reference": "BK-7XQ2M4PL", "status": "booked"},
             "status_updates": [{"text": "LH8400 MUC ORD"}]}
    return {
        "tracking": templates.tracking_text(session, lang),
        "tracking_update": templates.tracking_text(other, lang),
        "tracking_many": templates.tracking_many_text([session, other], lang),
        "tracking_unknown": templates.tracking_unknown_text(lang),
        "details": details_question_text(rfq),
        "pickup": templates.pickup_question_text(rfq),
        "requested": booking_requested_text(session),
        "reprice": templates.reprice_text(rfq, QUOTE),
        "reminder": templates.quote_reminder_text(rfq, QUOTE),
        "docs_ack": templates.docs_ack_text(rfq, QUOTE),
        "confirm": templates.confirm_text(rfq, QUOTE),
        "summary": quote_style.quote_summary_text(rfq, QUOTE, "Hi Lena, what was the price again?"),
    }


WITH_AMOUNT = {"reprice", "docs_ack", "confirm", "summary"}


def _check(lang: str, dg: bool, mails: dict[str, str]) -> None:
    for kind, text in mails.items():
        where = f"{lang}/{kind}"
        assert gate.MONEY.findall(text) == (["2,345.67"] if kind in WITH_AMOUNT else []), where
        if kind in WITH_AMOUNT:
            assert "EUR 2,345.67" in text, where
        assert not BANNED.search(text), where
        if kind.startswith("tracking") and kind != "tracking_unknown":
            assert "BK-50NN8E8G" in text or "BK-7XQ2M4PL" in text, where
            assert "MUC" in text and "ORD" in text and "Lumen Air Cargo" in text, where
        if kind in {"reminder", "confirm", "summary", "requested"}:
            assert "Lumen Air Cargo" in text, where
        if kind in {"reminder", "confirm", "summary"}:
            assert "MUC" in text and "ORD" in text, where
        if dg and kind in {"docs_ack", "summary"} and lang not in ("en", "de"):  # en/de: their own older DG wording
            assert "MSDS" in text and SDDG in text, where
        if dg and kind == "confirm":
            assert "DG" in text, where
        if lang != "en":
            assert not ENGLISH.search(text.replace(SDDG, "")), (where, text)


@pytest.mark.parametrize("lang", NATIVE)
@pytest.mark.parametrize("dg", [False, True])
def test_every_mail_in_each_template_language_without_a_model_call(lang, dg, monkeypatch):
    monkeypatch.setattr("llm.chat_json", lambda *a, **k: pytest.fail("no model call for a template language"))
    _check(lang, dg, _mails(lang, dg))


def test_english_wording_is_unchanged():
    mails = _mails("en", False)
    assert mails["tracking"].startswith("Hi Anna,") and "BK-50NN8E8G" in mails["tracking"]
    assert "yes, I can confirm: our offer covers 3 pieces" in mails["confirm"]
    assert "Of course, here is your quote again" in mails["summary"]


def test_the_last_line_has_no_full_stop_and_the_greeting_is_theirs():
    for lang in NATIVE[1:]:
        text = _mails(lang, False)["requested"]
        assert text.startswith(short_mail._hi(lang, "Anna")) and text.endswith(short_mail._sign(lang))
        assert not text.split("\n\n")[1].endswith(".")


FAKE_KO_CORE = {"hi": "안녕하세요", "sign": "감사합니다,\nLena",
                "quote": "{carrier}이(가) {goods}을 {origin}에서 {destination}까지 {amount} 올인으로 운송할 수 있습니다{pickup}.{transit}",
                "goods_one": "{n}개", "goods_many": "{n}개", "pickup": ", 픽업 포함", "transit": " 운송 기간은 약 {n}입니다.",
                "day_one": "{n}일", "day_many": "{n}일", "reply": "예약 시 공간이 확정됩니다, 예라고 답해 주시면 바로 예약합니다",
                "booked": "{airline}로 예약 완료, {origin}에서 {destination}, 예약번호 {ref}. 확정되면 알려드릴게요",
                "confirmed": "{airline}이(가) {ref}을(를) 확정했습니다. 언제든 상태를 물어보세요",
                "dg": "위험물(DG)입니다: 픽업 전에 Shipper's Declaration for Dangerous Goods와 MSDS를 보내주세요."}


def _fake_ko_more() -> dict:
    """A 'translation' that keeps every placeholder and the DG names (stands in for the model's Korean)."""
    out = {}
    for key, text in short_mail.MORE["en"].items():
        holes = re.findall(r"\{\w+\}", text)
        keep = f" {SDDG} MSDS" if key == "wait_dg" else ""
        out[key] = "한국어 " + " ".join(holes) + keep + " 문장"
    return out


@pytest.fixture
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(short_mail, "CACHE", tmp_path / "langs.json")
    monkeypatch.setattr(short_mail, "_tried", set())
    monkeypatch.setattr(short_mail, "MORE", dict(short_mail.MORE))
    for name in ("HI", "SIGN", "QUOTE", "GOODS", "PICKUP", "TRANSIT", "DAYS", "REPLY", "BOOKED", "CONFIRMED", "DG"):
        monkeypatch.setattr(short_mail, name, dict(getattr(short_mail, name)))


def test_a_translated_language_gets_every_mail_with_the_facts_from_code(fresh, monkeypatch):
    calls = []

    def fake(name, system, text, schema, **k):
        calls.append(set(json.loads(text)))
        return (dict(FAKE_KO_CORE) if "quote" in json.loads(text) else _fake_ko_more()), 0.0004
    monkeypatch.setattr("llm.chat_json", fake)
    for dg in (False, True):
        mails = _mails("ko", dg)
        for kind, text in mails.items():
            assert text.startswith("안녕하세요"), kind
            assert gate.MONEY.findall(text) == (["2,345.67"] if kind in WITH_AMOUNT else []), kind
            assert not BANNED.search(text), kind
        assert "EUR 2,345.67" in mails["reprice"] and "BK-50NN8E8G" in mails["tracking"]
        assert "Lumen Air Cargo" in mails["reminder"] and "MUC" in mails["reminder"]
        if dg:
            assert "MSDS" in mails["docs_ack"] and SDDG in mails["docs_ack"]
    assert len(calls) == 2  # core once + the other mails once, then cached
    cache = json.loads(short_mail.CACHE.read_text())
    assert "ko" in cache and "ko:more" in cache


def test_a_broken_translation_of_the_other_mails_means_english_and_keeps_the_quote(fresh, monkeypatch):
    def fake(name, system, text, schema, **k):
        if "quote" in json.loads(text):
            return dict(FAKE_KO_CORE), 0.0
        bad = _fake_ko_more()
        bad["reprice"] = bad["reprice"].replace("{amount}", "2.345,67 유로")  # the model touched the amount
        return bad, 0.0
    monkeypatch.setattr("llm.chat_json", fake)
    monkeypatch.setattr(quote_style, "QUOTE_STYLE", "short")
    rfq = {**RFQ, "language": "ko"}
    assert templates.reprice_text(rfq, QUOTE).startswith("Hi Anna,")  # English, amount intact
    assert templates.quote_text(rfq, {**QUOTE, "pickup": None}).startswith("안녕하세요")  # the quote keeps Korean


def test_a_session_tracking_question_follows_the_asking_mail_then_the_session():
    session = {"rfq": {**RFQ, "language": "de"}, "quote": QUOTE, "booking": BOOKING, "status_updates": []}
    english_q = language.wanted({"subject": "Status", "body": "Hi, could you tell me where our shipment is right now?"})
    assert templates.tracking_text(session, english_q).startswith("Hi Anna,")
    short_q = language.wanted({"subject": "BK-50NN8E8G", "body": "BK-50NN8E8G?"})
    assert short_q is None and templates.tracking_text(session, short_q).startswith("Hallo Anna,")
    zh_q = language.wanted({"subject": "货物状态", "body": "您好，请问我们的货物BK-50NN8E8G现在到哪里了？谢谢"})
    assert templates.tracking_text(session, zh_q).startswith("Anna，您好")


def test_off_switch_keeps_english_for_the_other_mails(monkeypatch):
    monkeypatch.setattr(language, "REPLY_LANGUAGE", False)
    rfq = {**RFQ, "language": "pl"}
    assert templates.confirm_text(rfq, QUOTE).startswith("Hi Anna,")
    assert templates.tracking_unknown_text("zh").startswith("Hi")
