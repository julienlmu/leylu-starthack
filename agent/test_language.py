"""R72 wrong_language: the customer's language read by code, and the last check on every reply."""

import pytest

import language
from inbox import FixtureMailbox

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
EN_QUOTE = ("Hi Petra,\n\nNova Atlas Cargo can fly your 11 pieces from CGN to LIM for EUR 2,914.56 all in, pickup included. "
            "Transit is about 3 days.\n\nJust reply and I'll book it\n\nThanks,\nLena")


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


def test_tonights_english_mails_stay_untouched(monkeypatch):
    monkeypatch.setattr(language, "REPLY_LANGUAGE", True)
    monkeypatch.setattr(language, "translate", lambda *a: pytest.fail("no translation for an English mail"))
    mail = {"subject": "Air freight quote to LIM", "body": "Hi,\n\nCould you quote an all-in price in EUR for the fastest "
            "air freight option to LIM (Lima, PE)? Please arrange truck pickup from our site in 61585 (Bad Homburg).\n\n"
            "Thanks\n\nMira Petersen\nNordlicht Audio"}
    assert language.guard(mail, EN_QUOTE) == EN_QUOTE


def _box_reply(monkeypatch, mail, body, translated):
    import llm
    monkeypatch.setattr(language, "REPLY_LANGUAGE", True)
    calls = []
    monkeypatch.setattr(llm, "chat_json", lambda name, system, text, schema, **k: (calls.append(system) or
                                                                                   ({"text": translated}, 0.0)))
    box = FixtureMailbox("/nonexistent")
    box.reply({**mail, "thread_id": 1}, body)
    return box.sent[0]["body"], calls


def test_r72_english_quote_to_a_chinese_rfq_is_translated(monkeypatch):
    zh = "您好 Petra，\n\nNova Atlas Cargo 可以将您的 11 件货物从 CGN 运到 LIM，全包价 EUR 2,914.56，含上门提货。运输时间约 3 天。\n\n谢谢，\nLena"
    sent, calls = _box_reply(monkeypatch, {"from": "hofmann@x", "subject": "空运询价", "body": R72}, EN_QUOTE, zh)
    assert sent == zh and "Chinese" in calls[0]


def test_a_translation_that_changes_the_amount_is_not_sent(monkeypatch):
    bad = "您好 Petra，\n\nNova Atlas Cargo 可以将您的 11 件货物从 CGN 运到 LIM，全包价 2914 欧元。\n\n谢谢，\nLena"
    sent, _ = _box_reply(monkeypatch, {"from": "hofmann@x", "subject": "空运询价", "body": R72}, EN_QUOTE, bad)
    assert sent == EN_QUOTE


def test_dg_document_names_must_survive(monkeypatch):
    body = EN_QUOTE + "\nPlease send the Shipper's Declaration for Dangerous Goods and the MSDS before pickup."
    lost = "您好，全包价 EUR 2,914.56。请在提货前发送危险品申报单和安全技术说明书。谢谢，Lena"
    sent, _ = _box_reply(monkeypatch, {"from": "hofmann@x", "subject": "空运询价", "body": R72}, body, lost)
    assert sent == body


def test_an_english_line_inside_a_german_reply_is_caught():
    de = ("Hallo Anna,\n\nNova Atlas Cargo kann Ihre 3 Packstücke von MUC nach SYD fliegen, für EUR 1.234,56 all-in.\n"
          "We have noted that the pieces must not be stacked and book the space accordingly.\n\nDanke und Grüße\nLena")
    assert language.needs_translation(de, "de")
    assert not language.needs_translation(de.replace(
        "We have noted that the pieces must not be stacked and book the space accordingly.",
        "Wir haben notiert, dass die Packstücke nicht gestapelt werden dürfen."), "de")


def test_a_failing_gateway_never_costs_the_reply(monkeypatch):
    import llm
    monkeypatch.setattr(language, "REPLY_LANGUAGE", True)

    def down(*a, **k):
        raise TimeoutError("gateway")
    monkeypatch.setattr(llm, "chat_json", down)
    assert language.guard({"subject": "x", "body": R72}, EN_QUOTE) == EN_QUOTE


def test_off_switch(monkeypatch):
    monkeypatch.setattr(language, "translate", lambda *a: pytest.fail("off means off"))
    assert language.guard({"subject": "x", "body": R72}, EN_QUOTE) == EN_QUOTE  # conftest: REPLY_LANGUAGE off


def test_the_models_reply_wish_is_kept_and_an_explicit_one_wins():
    de = {"subject": "Anfrage", "body": "Guten Tag,\nbitte bieten Sie uns die günstigste Option nach LIM an. 11 Stück, "
                                        "704 kg. Unser Kollege in Lima liest nur Englisch mit.\nDanke"}
    # the model read "reply in English" from "liest nur Englisch mit": the code doesn't undo it
    assert language.for_rfq(de, {"language": "en", "mail_language": "de"}) is None
    # the model said German for a Chinese mail: the text wins
    assert language.for_rfq({"subject": "x", "body": R72}, {"language": "en", "mail_language": "en"}) == "zh"
    asked = {"subject": "x", "body": "您好，想请您报一票发往LIM的空运，共11件，704 kg。请用英文回复，谢谢！"}
    assert language.for_rfq(asked, {"language": "zh", "mail_language": "zh"}) == "en"
    assert language.for_rfq({"subject": "x", "body": R72}, {"language": "zh", "mail_language": "zh"}) is None


def test_a_reply_in_a_language_the_mail_names_is_never_translated(monkeypatch):
    monkeypatch.setattr(language, "REPLY_LANGUAGE", True)
    monkeypatch.setattr(language, "translate", lambda *a: pytest.fail("the customer named English"))
    mail = {"subject": "Anfrage", "body": "Guten Tag,\nbitte bieten Sie uns die günstigste Option nach LIM an. 11 Stück, "
                                          "704 kg. Unser Kollege in Lima liest nur Englisch mit.\nDanke"}
    assert language.guard(mail, EN_QUOTE) == EN_QUOTE
