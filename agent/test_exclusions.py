import exclusions

CARRIERS = [{"name": "Zephyr Steppe Cargo", "kind": "airline"}, {"name": "Lumen Air Cargo", "kind": "airline"},
            {"name": "Lumen Air", "kind": "airline"}, {"name": "Kranich Kurier", "kind": "trucker"}]
R42 = ("Hi,\n\nCould you quote your cheapest air freight option to ULN? Please do not offer Zephyr Steppe Cargo (ZS) "
       "for this shipment or for any of our future inquiries.\n\nThanks\nMeyer Industrietechnik")


def test_round_42_sentence_and_a_code_only_mention(tmp_path, monkeypatch):
    monkeypatch.setattr(exclusions, "STORE", tmp_path / "x.json")
    assert exclusions.found_in_mail(R42, CARRIERS) == ["Zephyr Steppe Cargo", "ZS"]
    assert exclusions.found_in_mail("Please don't use (ZS) this time.", CARRIERS) == ["ZS"]
    assert exclusions.found_in_mail("Bitte ohne Zephyr Steppe Cargo.", CARRIERS) == ["Zephyr Steppe Cargo"]
    assert exclusions.for_customer("meyer@x.example", R42, CARRIERS) == ["Zephyr Steppe Cargo", "ZS"]
    assert exclusions.for_customer("meyer@x.example", "Please quote to ULN.", CARRIERS) == ["Zephyr Steppe Cargo", "ZS"]
    assert exclusions.for_customer("other@x.example", "Please quote to ULN.", CARRIERS) == []
    # this shipment only: not remembered
    once = "Please do not offer Zephyr Steppe Cargo for this one."
    assert exclusions.for_customer("once@x.example", once, CARRIERS) == ["Zephyr Steppe Cargo"]
    assert exclusions.for_customer("once@x.example", "Please quote to ULN.", CARRIERS) == []


def test_no_false_positives():
    for text in ("We do not mind which airline, Lumen Air was great last time.",
                 "Wir sind nicht festgelegt, gerne auch Lumen Air.",
                 "Avoid delays please, we used Lumen Air before.",
                 "Bitte nur mit Lumen Air Cargo, keine Umladung.",
                 "Keine Umladung, bitte nur Lumen Air Cargo.",
                 "Kein Problem mit Lumen Air Cargo.",
                 "Lumen Air Cargo was great last time, please quote.",
                 "Please quote, it is not dangerous goods (UN) and fine with Lumen Air Cargo."):
        assert exclusions.found_in_mail(text, CARRIERS) == [], text


def test_a_list_of_excluded_airlines_excludes_all_of_them():
    from carriers import load_carriers
    cs = load_carriers()
    assert set(exclusions.found_in_mail("Please exclude Fjordline Air Cargo and Helix Air Freight.", cs)) == {
        "Fjordline Air Cargo", "Helix Air Freight"}
    assert exclusions.found_in_mail("We do not mind which airline, Lumen Air Cargo was great.", cs) == []
