**Task:** R85 too_high · **Agent:** Claude Code

# Arrive-by deadline counts the flight, not the trucker's hours (DEADLINE_AIR)
- Who: Orhun (tool: Claude Code)
- Branch: orhun/human-mail (deploy branch, on main 90aeec7)
- What happened in R85: Augsburg → MUC-YYZ, cheapest, ready 27 Nov, "must arrive by 1 Dec". `gate._arrives` added the option's whole transit (3-day flight + 31 h pickup = 4.29 → 5 days, 2 Dec), so Lumen (EUR 2,588.00) was dropped and Aurelia (EUR 3,778.40) quoted. 5U counted Lumen as arriving 30 Nov, and 7 teams were accepted.
- What changed: `gate._arrives` now uses ready date + ceil(flight transit), where flight = option transit − pickup transit. Airport-to-airport options are unchanged. `DEADLINE_AIR=off` gives the old behaviour.
- Tests: `test_gate.py::test_r85_deadline_counts_the_flight_not_the_truck`, using R85's numbers (picks Lumen at 2,588.00; Riverbend at 5 days is still out). The full suite passes.
- New env vars: DEADLINE_AIR (default on).
