"""MODE_DECLINE: a sea, road, rail or courier request gets an honest decline with no amount, never an air quote
(sweep 22 Nov; session 184 sea FCL HAM → JEA). Air named anywhere (a pickup by truck to the airport) is never caught."""
import pytest

import mode_decline
from test_rfq_shape_sweep import CANNED, Api, backend_url, isolated, mail, piece, raw, run  # noqa: F401


@pytest.mark.parametrize("body", [
    "Please quote sea freight FCL 40' DEHAM to AEJEA, 18 t general cargo.",
    # session 184
    "Could you send me an all-in price in EUR for a port-to-port sea freight shipment from Hamburg (DEHAM) to Jebel Ali "
    "(AEJEA)? It's an FCL shipment in 1 x 40ft container, with 6 pieces, a gross weight of 9617 kg.",
    "Road freight please: LTL truck from Stuttgart to Milan, 2 pallets 600 kg.",
    "Can you send a 2 kg document envelope by courier (DHL/UPS) to New York?",
    "Rail freight China-Europe, Duisburg to Chengdu, 1 container.",
    "1 x 40ft HC container Hamburg to Shanghai, 12 t.",
    "Seefracht Hamburg - Shanghai, 1x20' Container, 8 t.",
    "Bitte ein Angebot für einen Straßentransport von München nach Wien, 3 Paletten.",
    "Merci de coter un fret maritime Hambourg - Montréal, 4 palettes.",
])
def test_other_modes_are_caught(body):
    assert mode_decline.caught({"subject": "Quote request", "body": body})


@pytest.mark.parametrize("body", [
    # sessions 73, 87, 124 (won or quoted): the truck is the pickup to the departure airport
    "Bitte organisieren Sie die Abholung und den Lkw-Transport zum Abflughafen. Luftfracht nach RUH.",
    "Could you please quote an all-in price in EUR for air freight to YYZ, including collection by truck from our site.",
    "Please provide an all-in price in EUR, including the pickup and road transport to the departure airport.",
    "We usually ship by sea, but this time please quote air freight HAM-JFK.",
    "Please quote FRA to JFK, 300 kg, pickup by truck from our warehouse in Mainz.",
    "Our courier will hand the goods over at FRA. 120 kg to ORD.",
    "One steel pipe, 20 ft long, 300 kg, MUC to DXB.",
    "3 pallets, 420 kg, FRA to ORD, cheapest please.",
])
def test_air_or_no_mode_word_is_never_caught(body):
    assert mode_decline.caught({"subject": "Quote request", "body": body}) is None


def test_off(monkeypatch):
    monkeypatch.setattr(mode_decline, "ON", False)
    assert mode_decline.caught({"subject": "Sea freight quote", "body": "FCL 40ft"}) is None


def test_the_sea_request_gets_the_decline_and_no_amount(monkeypatch, tmp_path, backend_url):  # noqa: F811
    api = Api(backend_url, canned=CANNED)
    m = mail("Please quote sea freight FCL 40' Hamburg to Jebel Ali, 6 pieces, 9617 kg.", subject="Sea freight quote")
    _, sent = run(monkeypatch, tmp_path, api, m, raw(origin="HAM", destination="DXB", pieces=[piece(6, 9617)]))
    assert len(sent) == 1 and "only offer air freight" in sent[0]["body"]
    assert "EUR" not in sent[0]["body"] and api.quote() is None and api.priced == []
    session = api.find(m["thread_id"])
    assert session["stage"] == "done" and session["outcome"] == "lost" and not session["needs_human"]


def test_german_text(monkeypatch, tmp_path, backend_url):  # noqa: F811
    api = Api(backend_url, canned=CANNED)
    m = mail("Seefracht Hamburg - Shanghai, 1x20' Container, 8000 kg.", subject="Anfrage")
    _, sent = run(monkeypatch, tmp_path, api, m, raw(origin="HAM", destination="PVG", pieces=[piece(1, 8000)],
                                                    language="de"))
    assert len(sent) == 1 and "nur Luftfracht" in sent[0]["body"]


def test_an_air_request_with_a_truck_pickup_is_still_quoted(monkeypatch, tmp_path, backend_url):  # noqa: F811
    api = Api(backend_url, canned=CANNED)
    m = mail("Air freight FRA to ORD, 3 pallets 420 kg, collection by truck from our site.")
    _, sent = run(monkeypatch, tmp_path, api, m, raw())
    assert api.quote() is not None and "only offer air freight" not in sent[0]["body"]
