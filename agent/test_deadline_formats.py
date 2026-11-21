import importlib
from datetime import date

import pytest

import gate

READY = date(2026, 11, 24)


@pytest.mark.parametrize("text, expected", [
    ("It must arrive by 28/11/2026.", date(2026, 11, 28)),
    ("It must arrive by 11/28/2026.", date(2026, 11, 28)),  # US order only when the day can't be first
    ("Delivery needed latest November 28.", date(2026, 11, 28)),
    ("Needs to be there by the 28th of November.", date(2026, 11, 28)),
    ("Delivery needed by 28.11.", date(2026, 11, 28)),
    ("Must arrive by January 5.", date(2027, 1, 5)),  # no year, before the ready date: next year
    ("La merce deve arrivare entro il 28.11.2026.", date(2026, 11, 28)),
    ("Consegna entro il 28 novembre.", date(2026, 11, 28)),
    ("Debe llegar a más tardar el 28/11/2026.", date(2026, 11, 28)),
    ("Livraison au plus tard le 28 novembre 2026.", date(2026, 11, 28)),
    ("Levering uiterlijk op 28.11.2026.", date(2026, 11, 28)),
    ("Dostawa najpóźniej do 28.11.2026.", date(2026, 11, 28)),
    ("It must arrive by 2026-11-28.", date(2026, 11, 28)),  # unchanged formats
    ("spätestens am 30.11.2026", date(2026, 11, 30)),
])
def test_deadlines_in_more_formats_and_languages(text, expected):
    assert gate.deadline(text, READY) == expected


@pytest.mark.parametrize("text", [
    "Ready for pickup on 28/11/2026.",  # a ready date is no deadline
    "Our reference 28/11 is on the crates.",
    "Please quote by 25.11.",  # a deadline for our answer, not the arrival
    "Cheapest option please, 3 pieces, 715 kg.",
])
def test_no_deadline_where_the_customer_names_none(text):
    assert gate.deadline(text, READY) is None


def test_deadline_formats_off_keeps_the_old_formats(monkeypatch):
    monkeypatch.setenv("DEADLINE_FORMATS", "off")
    try:
        old = importlib.reload(gate)
        assert old.deadline("It must arrive by 28/11/2026.", READY) is None
        assert old.deadline("Delivery needed latest November 28.", READY) is None
        assert old.deadline("It must arrive by 2026-11-28.", READY) == date(2026, 11, 28)
        assert old.deadline("It must arrive by 28.11.2026.", READY) == date(2026, 11, 28)
    finally:
        monkeypatch.delenv("DEADLINE_FORMATS")
        importlib.reload(gate)
