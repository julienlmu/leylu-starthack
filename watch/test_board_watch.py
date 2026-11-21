import json
from pathlib import Path

from board_watch import best_price, check, check_public, report, ts

FIX = Path(__file__).with_name("fixtures")
ME = json.loads((FIX / "me.json").read_text())
BOARD = json.loads((FIX / "board.json").read_text())
REAL = json.loads((FIX / "board_real.json").read_text(encoding="utf-8"))  # public board, Sat 16:17, rounds 1-3


def fresh():
    return {"seen": [], "reasons": [], "streak": 0}


# ---- public mode -------------------------------------------------------------------------------------------

def test_report_on_the_real_board_finds_our_round_1_miss():
    lines = report(REAL)
    assert "Round 1" in lines[0] and "field booked Meridian Freightways (5 teams)" in lines[0]
    assert "we did not book" in lines[0]  # the door-to-port RFQ #269 we handed to a person
    assert "we booked Solace Air Cargo" in lines[1] and "we booked Fjordline Air Cargo" in lines[2]


def board(answered, accepted, total, status, bookings=()):
    sent, expires = "2026-11-21T16:00:00+00:00", "2026-11-21T16:06:00+00:00"
    rounds = [{"round_no": 9, "status": status, "voided": False, "sent_at": sent, "expires_at": expires,
               "answered": 10, "accepted": 7}] if status else []
    return {"ranking": [{"name": "leylu", "team": "Leylü", "answered": answered, "accepted": accepted, "total": total}],
            "rounds": rounds,
            "bookings": [{"team": t, "airline": a, "booked_at": "2026-11-21T16:01:30+00:00"} for t, a in bookings]}


T0 = ts("2026-11-21T16:00:00+00:00")
IDLE = board(8, 7, 300.0, None)  # the watcher runs before round 9 starts (a round open at start-up is skipped)
FIELD = [("Mythos", "Meridian Freightways"), ("Google", "Meridian Freightways"), ("PIXEL", "Meridian Freightways")]


def test_no_answer_alerts_at_1_30_and_at_close():
    state = fresh()
    assert check_public(state, IDLE, T0 - 30) == []  # first poll = baseline
    assert check_public(state, board(8, 7, 300.0, "open"), T0 + 80) == []  # 1:20, still time
    assert check_public(state, board(8, 7, 300.0, "open"), T0 + 100) == [
        (True, "Round 9: no answer from us after 1:40 (10 teams answered): open the Sessions UI")]
    assert check_public(state, board(8, 7, 300.0, "open"), T0 + 115) == []  # once per round
    assert check_public(state, board(8, 7, 300.0, "closed", FIELD), T0 + 400) == [
        (True, "Round 9 closed with NO answer from us: field booked Meridian Freightways (3 teams)")]


def test_late_answer_clears_the_no_answer_alert():
    state = fresh()
    check_public(state, IDLE, T0 - 30)
    check_public(state, board(8, 7, 300.0, "open"), T0 + 100)  # alert at 1:40 (a slow carrier, say)
    assert check_public(state, board(9, 8, 360.0, "open"), T0 + 110) == [(True, "Round 9: answered at 1:50 after all")]


def test_accepted_round_reports_points_and_how_far_above_best():
    state = fresh()
    check_public(state, IDLE, T0 - 30)
    assert check_public(state, board(9, 8, 349.14, "open"), T0 + 50) == []  # answer + verdict in the same poll
    out = check_public(state, board(9, 8, 349.14, "closed", [*FIELD, ("Leylü", "Meridian Freightways")]), T0 + 400)
    assert out == [(False, "Round 9 accepted: +49.14 pts, about 1.2% above the best price")]


def test_answered_but_rejected_alerts_immediately():
    state = fresh()
    check_public(state, IDLE, T0 - 30)
    assert check_public(state, board(9, 7, 300.0, "open"), T0 + 40) == [
        (True, "Round 9: answered but NOT accepted (7/10 teams accepted)")]
    assert check_public(state, board(9, 7, 300.0, "closed", FIELD), T0 + 400) == [
        (True, "Round 9 not accepted: field booked Meridian Freightways (3 teams), we booked nothing")]


def test_a_late_verdict_clears_the_not_accepted_alert():
    state = fresh()
    check_public(state, IDLE, T0 - 30)
    check_public(state, board(9, 7, 300.0, "open"), T0 + 40)
    assert check_public(state, board(9, 8, 360.0, "open"), T0 + 55) == [(True, "Round 9: accepted after all (+60.00)")]


def test_a_failed_push_never_stops_the_watcher(monkeypatch):
    import board_watch

    def offline(*args, **kwargs):
        raise OSError("network is unreachable")

    monkeypatch.setenv("NTFY_TOPIC", "test-topic")
    monkeypatch.setattr(board_watch.urllib.request, "urlopen", offline)
    board_watch.notify("Board watcher can't reach 5U")  # must not raise


# ---- key mode ----------------------------------------------------------------------------------------------

def test_best_price_from_accuracy():
    assert best_price(1000, 45) == 1000  # full points: we were the best
    assert round(best_price(1050, 0), 2) == 1000  # zero points: exactly 5% above best
    assert round(best_price(1310, 27), 2) == 1284.31


def test_alerts_for_fixture_rounds():
    text = "\n".join(check(fresh(), ME, BOARD))
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
