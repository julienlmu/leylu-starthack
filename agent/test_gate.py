

def test_r85_deadline_counts_the_flight_not_the_truck():
    import gate
    """R85 (too_high): ready 27 Nov, arrive by 1 Dec; Lumen's 3-day flight + 31 h pickup arrives 30 Nov (5U), in time."""
    from datetime import date
    pickup = {"carrier": "Neckarstrom Kurier", "total": 108.0, "transit_days": 1.2916666666666667}
    lumen = {"carrier": "Lumen Air Cargo", "total": 2588.0, "transit_days": 4.291666666666667, "pickup": pickup}
    riverbend = {"carrier": "Riverbend Airlines Cargo", "total": 2848.4, "transit_days": 6.291666666666667, "pickup": pickup}
    aurelia = {"carrier": "Aurelia Air Cargo", "total": 3778.4, "transit_days": 3.291666666666667, "pickup": pickup}
    ready, by = date(2026, 11, 27), date(2026, 12, 1)
    ok = [o for o in (lumen, riverbend, aurelia) if (gate._arrives(o, ready) or date.max) <= by]
    assert min(ok, key=lambda o: o["total"]) is lumen and riverbend not in ok
    assert gate._arrives({"transit_days": 3.2}, ready) == date(2026, 12, 1)  # airport to airport: unchanged
