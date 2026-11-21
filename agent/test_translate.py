import templates


def test_a_language_without_template_is_translated_keeping_amounts(monkeypatch):
    import llm
    monkeypatch.setattr(llm, "chat_json", lambda name, system, text, schema, *a, **k: (
        {"text": "您好，总价 EUR 2,099.47，参考号 BK-ABCD1234。"}, 0.0))
    # zh has short templates since #177 (no per-mail call): a language short_mail neither has nor tried
    out = templates.localize({"language": "vi"}, "Hello, the all-in price is EUR 2,099.47, booking BK-ABCD1234.")
    assert out.startswith("您好") and "2,099.47" in out


def test_a_translation_that_loses_the_amount_falls_back_to_english(monkeypatch):
    import llm
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: ({"text": "您好，总价两千欧元。"}, 0.0))
    text = "Hello, the all-in price is EUR 2,099.47."
    assert templates.localize({"language": "vi"}, text) == text


def test_template_languages_and_english_are_never_sent_to_the_model(monkeypatch):
    import llm
    def boom(*a, **k):
        raise AssertionError("no call")
    monkeypatch.setattr(llm, "chat_json", boom)
    for code in ("en", "de", "fr", "tr"):
        assert templates.localize({"language": code}, "Hello EUR 1.00") == "Hello EUR 1.00"



def test_weights_lose_the_thousands_comma_outside_english():
    assert templates.localize({"language": "fr"}, "Pour vos 11 colis (1,497 kg), EUR 2,099.47") == \
        "Pour vos 11 colis (1497 kg), EUR 2,099.47"
    assert templates.localize({"language": "en"}, "11 pieces (1,497 kg)") == "11 pieces (1,497 kg)"
