import json
from pathlib import Path

from board_watch import accuracy_gap, best_price, check, check_bookings, check_public, report, time_points, ts

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


def test_no_answer_alerts_inside_the_round_and_at_close():
    state = fresh()
    assert check_public(state, IDLE, T0 - 30) == []  # first poll = baseline
    assert check_public(state, board(8, 7, 300.0, "open"), T0 + 100) == []  # 1:40, still time
    assert check_public(state, board(8, 7, 300.0, "open"), T0 + 160) == [
        (True, "Round 9: no answer from us after 2.7 min (10 teams answered): open the Sessions UI")]
    assert check_public(state, board(8, 7, 300.0, "closed", FIELD), T0 + 400) == [
        (True, "Round 9 closed with NO answer from us: field booked Meridian Freightways (3 teams)")]


def test_accepted_round_reports_points_and_how_far_off_best():
    state = fresh()
    check_public(state, IDLE, T0 - 30)
    check_public(state, board(9, 7, 300.0, "open"), T0 + 50)  # we answered at ~0:50
    check_public(state, board(9, 8, 349.14, "open"), T0 + 80)  # accepted: +49.14 (live round 2: 2.41 % above best)
    out = check_public(state, board(9, 8, 349.14, "closed", [*FIELD, ("Leylü", "Meridian Freightways")]), T0 + 400)
    assert out == [(True, "Round 9 accepted: +49.14 pts, about 2.4% off the best price (above or below)")]


def test_full_points_say_nothing_about_the_price():
    state = fresh()
    check_public(state, IDLE, T0 - 30)
    check_public(state, board(9, 7, 300.0, "open"), T0 + 40)
    check_public(state, board(9, 8, 360.0, "open"), T0 + 70)
    assert check_public(state, board(9, 8, 360.0, "closed"), T0 + 400) == [(False, "Round 9 accepted: +60.00 pts")]


def test_scoring_model_matches_live_rounds():
    assert time_points(45) == 15 and round(time_points(138.78), 2) == 13.83 and time_points(400) == 0  # round 7
    assert round(accuracy_gap(49.14, 45), 4) == 0.0241  # round 2: +2.41 % (fastest trucker instead of balanced)
    assert round(accuracy_gap(45.59, 40), 4) == 0.032  # round 9: -3.20 % (cheapest trucker instead of balanced)
    assert accuracy_gap(58.83, 138.78) < 0.0005  # round 7: late but exact


def test_tracking_bonus_and_hourly_cost_points():
    state = fresh()
    check_public(state, IDLE, T0 - 30)
    check_public(state, board(9, 7, 300.0, "open"), T0 + 40)
    check_public(state, board(9, 8, 360.0, "open"), T0 + 70)
    assert check_public(state, board(9, 8, 370.0, "closed"), T0 + 700) == [
        (False, "Tracking bonus +10"), (False, "Round 9 accepted: +60.00 pts")]
    assert state["bonus_at"] == [T0 + 700]
    # 17:06 UTC: cost points for the 16:00-17:00 hour, one accepted quote (round 9 started 16:00)
    assert check_public(state, board(9, 8, 409.8, "closed"), T0 + 3960) == [
        (False, "Hourly cost points +39.80 for 1 accepted quotes of 16:00-17:00 UTC = 39.80 each (max 40): fine")]
    assert check_public(state, board(9, 8, 409.8 + 39.1, "closed"), T0 + 7560)[0][0] is False  # no accepted that hour
    state["rounds"]["9"]["sent"] = "2026-11-21T17:00:00+00:00"  # one accepted 17:00-18:00 at 37 points: push
    assert check_public(state, board(9, 8, 409.8 + 39.1 + 37.0, "closed"), T0 + 7570)[0][0] is True


def me_rows(*rows):
    return {"requests": [{"round_no": n, "sent_at": sent, "verdict": "accepted", "reason": None, "booked": booked}
                         for n, sent, booked in rows]}


def test_booking_alerts():
    s = "2026-11-21T16:00:00+00:00"
    state = {"booking_baseline": True, "bonus_at": [T0 + 11 * 60]}
    me = me_rows((5, s, False), (6, s, True), (7, s, None))
    assert check_bookings(state, me, T0 + 200) == [  # round 5 flagged at once; 7 still inside its round
        "Round 5: 5U doesn't count a booking for it (booked: false), so no tracking question and no +10. "
        "Booked weight below the real weight, a wrong rate, or nothing booked?"]
    assert check_bookings(state, me, T0 + 400) == [
        "Round 7 accepted but not booked: no tracking +10 unless we book it (a manual quote?)"]
    assert check_bookings(state, me, T0 + 15 * 60) == []  # round 6 got its +10 at 11 min
    assert state["bonus_at"] == []
    state = {"booking_baseline": True}
    assert check_bookings(state, me_rows((8, s, True)), T0 + 15 * 60) == [
        "Round 8: booked, but no +10 tracking bonus 14 min later: check the tracking answer"]


def test_booking_alerts_skip_history_on_first_run():
    old = "2026-11-21T15:00:00+00:00"
    assert check_bookings({}, me_rows((1, old, False), (2, old, None)), T0) == []


def test_answered_but_rejected():
    state = fresh()
    check_public(state, IDLE, T0 - 30)
    check_public(state, board(9, 7, 300.0, "open"), T0 + 40)
    assert check_public(state, board(9, 7, 300.0, "open"), T0 + 110) == [
        (True, "Round 9: answered but not accepted after 60 s (7/10 teams accepted)")]
    assert check_public(state, board(9, 7, 300.0, "closed", FIELD), T0 + 400) == [
        (True, "Round 9 not accepted: field booked Meridian Freightways (3 teams), we booked nothing")]


# ---- key mode ----------------------------------------------------------------------------------------------

def test_best_price_from_accuracy():
    assert best_price(1000, 45) == 1000  # full points: we were the best
    assert round(best_price(1100, 0), 2) == 1000  # zero points: 10 % above best
    assert round(best_price(1310, 27), 2) == 1259.62


def test_alerts_for_fixture_rounds():
    text = "\n".join(check(fresh(), ME, BOARD))
    assert "we were 4.0% high" in text  # round 1: accepted, 27/45
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
