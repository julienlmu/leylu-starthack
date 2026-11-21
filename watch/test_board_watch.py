import json
from pathlib import Path

from board_watch import best_price, check

ME = json.loads(Path(__file__).with_name("fixtures").joinpath("me.json").read_text())
BOARD = json.loads(Path(__file__).with_name("fixtures").joinpath("board.json").read_text())


def fresh():
    return {"seen": [], "reasons": [], "streak": 0}


def test_best_price_from_accuracy():
    assert best_price(1000, 45) == 1000  # full points: we were the best
    assert round(best_price(1050, 0), 2) == 1000  # zero points: exactly 5% above best
    assert round(best_price(1310, 27), 2) == 1284.31


def test_alerts_for_fixture_rounds():
    alerts = check(fresh(), ME, BOARD)
    text = "\n".join(alerts)
    assert "we were 2.0% high" in text  # round 1: accepted, 27/45
    assert "reason code 'NO_REPLY'" in text and "reason code 'PRICE_TOO_HIGH'" in text
    assert "Round 3 rejected (PRICE_TOO_HIGH), 4 other team(s)" in text  # a better price existed
    assert "Two failed requests in a row" in text  # rounds 2 and 3
    assert "Round 4" not in text  # still open: not scored yet


def test_each_round_alerts_once():
    state = fresh()
    check(state, ME, BOARD)
    assert check(state, ME, BOARD) == []


def test_unknown_fields_warn_once_instead_of_going_quiet():
    me = {"results": [{"rnd": 1, "status": "accepted"}]}
    state = fresh()
    assert check(state, me, {}) == ["board/me fields not recognised (rnd, status): fix requests_of()"]
    assert check(state, me, {}) == []
