"""Extraction eval: real and hard RFQs → read_request() → is the price input right?

Run from agent/:  uv run --env-file ../.env python evals/extract_eval.py [--replay raw.json] [--save raw.json] [--only N]
--save records every model answer; --replay feeds recorded answers back (no gateway call, $0), so changes to the code
checks can be compared for free. Only a prompt or schema change needs a live run (gpt-6-luna ~$0.0001 per mail; it
counts towards the hour's LLM cost on the leaderboard, so keep live runs rare).

Verdicts: ok · person (handed over: safe, but scores 0) · WRONG (priced from a wrong reading: the quote is rejected).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))  # the agent/ folder being evaluated
import extract  # noqa: E402

CASES = Path(__file__).with_name("rfq_cases.json")


def chargeable(weight_kg: float, volume_m3: float) -> float:
    return max(weight_kg, volume_m3 * 167)


def judge(rfq: dict, missing: list, expect: dict) -> tuple[str, list[str]]:
    if missing:
        return "person", [f"missing {', '.join(missing)}"]
    pieces = rfq["pieces"]
    kg = sum(p["count"] * (p["weight_kg"] or 0) for p in pieces)
    m3 = rfq["volume_m3"]
    if m3 is None:
        m3 = sum(p["count"] * p["length_cm"] * p["width_cm"] * p["height_cm"] for p in pieces) / 1e6
    got, want = chargeable(kg, m3), chargeable(expect["weight_kg"], expect["volume_m3"])
    wrong = [f"{f} {rfq.get(f)!r} != {expect[f]!r}" for f in ("origin", "destination", "ask", "ready_date")
             if rfq.get(f) != expect[f]]
    if bool(rfq.get("pickup")) != expect["door"]:
        wrong.append(f"door-to-port {bool(rfq.get('pickup'))} != {expect['door']}")
    if abs(got - want) > 0.02 * want:
        wrong.append(f"chargeable {got:.1f} kg != {want:.1f} kg ({kg:.1f} kg, {m3:.3f} m3)")
    if expect.get("dangerous_goods") and not rfq.get("dangerous_goods"):
        wrong.append("dangerous goods not flagged")
    return ("WRONG" if wrong else "ok"), wrong


def main() -> None:
    args = argparse.ArgumentParser()
    args.add_argument("--replay")
    args.add_argument("--save")
    args.add_argument("--only", type=int)
    args.add_argument("--cases", default=str(CASES))
    a = args.parse_args()
    cases = json.load(open(a.cases))[: a.only]
    recorded = json.load(open(a.replay)) if a.replay else {}
    raw_log: dict[str, dict] = {}
    live_extract = extract.extract

    def recording_extract(mail, model=extract.llm.MODEL):
        key = f"{mail['id']}|{model}"
        if a.replay:
            if key not in recorded:
                raise RuntimeError(f"no recorded answer for {key}")
            raw, cost = recorded[key]["raw"], recorded[key]["cost"]
        else:
            raw, cost = live_extract(mail, model)
        raw_log[key] = {"raw": raw, "cost": cost}
        return raw, cost

    extract.extract = recording_extract
    tally, total_cost = {"ok": 0, "person": 0, "WRONG": 0}, 0.0
    for case in cases:
        try:
            read = extract.read_request(case["mail"])
            verdict, notes = judge(read["rfq"], read["missing"], case["expect"])
            cost, how = read["cost"], read["model"] + (" (escalated)" if read["escalated"] else "")
        except Exception as error:  # a crash is a lost RFQ
            verdict, notes, cost, how = "person", [f"crash {type(error).__name__}: {error}"], 0.0, "-"
        tally[verdict] += 1
        total_cost += cost
        print(f"{verdict:6} {case['name'][:45]:45} {how:28} ${cost:.5f}  {'; '.join(notes)}")
    print(f"\n{tally['ok']} ok · {tally['person']} to a person · {tally['WRONG']} WRONG · of {len(cases)} · "
          f"LLM ${total_cost:.4f}{' (replayed, $0 spent)' if a.replay else ''}")
    if a.save:
        json.dump(raw_log, open(a.save, "w"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
