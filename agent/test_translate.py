import templates


def test_a_finished_mail_never_passes_through_the_model(monkeypatch):
    """Review of #188: languages without a template go through short_mail's cached templates, never whole-mail translation."""
    import llm

    def boom(*a, **k):
        raise AssertionError("no call")
    monkeypatch.setattr(llm, "chat_json", boom)
    for code in ("en", "de", "fr", "tr", "zh", "ja"):
        assert templates.localize({"language": code}, "Hello EUR 1.00") == "Hello EUR 1.00"


def test_weights_lose_the_thousands_comma_outside_english():
    assert templates.localize({"language": "fr"}, "Pour vos 11 colis (1,497 kg), EUR 2,099.47") == \
        "Pour vos 11 colis (1497 kg), EUR 2,099.47"
    assert templates.localize({"language": "en"}, "11 pieces (1,497 kg)") == "11 pieces (1,497 kg)"
