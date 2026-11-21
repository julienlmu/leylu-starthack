import exclusions

CARRIERS = [{"name": "Zephyr Steppe Cargo", "kind": "airline"}, {"name": "Lumen Air Cargo", "kind": "airline"},
            {"name": "Kranich Kurier", "kind": "trucker"}]
R42 = ("Hi,\n\nCould you quote your cheapest air freight option to ULN? Please do not offer Zephyr Steppe Cargo (ZS) "
       "for this shipment or for any of our future inquiries.\n\nThanks\nMeyer Industrietechnik")


def test_round_42_sentence_and_a_code_only_mention(tmp_path, monkeypatch):
    monkeypatch.setattr(exclusions, "STORE", tmp_path / "x.json")
    assert exclusions.found_in_mail(R42, CARRIERS) == ["Zephyr Steppe Cargo", "ZS"]
    assert exclusions.found_in_mail("We don't want to fly with (ZS) this time.", CARRIERS) == ["ZS"]
    assert exclusions.found_in_mail("Lumen Air Cargo was great last time, please quote.", CARRIERS) == []
    # remembered for this customer's next RFQ, not for others
    assert exclusions.for_customer("meyer@x.example", R42, CARRIERS) == ["Zephyr Steppe Cargo", "ZS"]
    assert exclusions.for_customer("meyer@x.example", "Please quote to ULN.", CARRIERS) == ["Zephyr Steppe Cargo", "ZS"]
    assert exclusions.for_customer("other@x.example", "Please quote to ULN.", CARRIERS) == []
