// Scoreboard: an ESTIMATE of 5U points per round, computed from sessions only (no new endpoint).
// Weights are the board's rules object (KIT_SUMMARY §9): accuracy 45, cost 40, time 15, tracking 10.
// The real verdicts live on /v1/board/me, which the UI does not call; this view only shows the shape.
import { COST_CAP_USD, RESPONSE_FULL_S, RESPONSE_ZERO_S } from "./metrics";
import type { Session } from "./types";

export const WEIGHTS = { accuracy: 45, cost: 40, time: 15, tracking: 10 } as const;
export type Part = keyof typeof WEIGHTS;
export const PARTS: Part[] = ["accuracy", "time", "cost", "tracking"];

// A new mail lands every 6 minutes; rounds start at :53:56 of the hour + n × 6 min, so every round
// boundary sits 356 s past a multiple of 360 s since the epoch.
const ROUND_S = 360;
const ROUND_OFFSET_S = 356;
export const roundOf = (iso: string) => Math.floor((Date.parse(iso) / 1000 - ROUND_OFFSET_S) / ROUND_S);
export const roundStart = (r: number) => new Date((r * ROUND_S + ROUND_OFFSET_S) * 1000).toISOString();

export type Leak = "late" | "unquoted" | "lost" | "cost";
export type SessionScore = { session: Session; points: Record<Part, number>; total: number; leaks: Partial<Record<Leak, number>> };
export type RoundScore = { round: number; n: number; start: string; sessions: SessionScore[]; points: Record<Part, number>; total: number };

const zero = (): Record<Part, number> => ({ accuracy: 0, cost: 0, time: 0, tracking: 0 });
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

export function scoreSession(s: Session): SessionScore {
  const p = zero();
  const leaks: SessionScore["leaks"] = {};
  if (!s.quote) {
    leaks.unquoted = WEIGHTS.accuracy + WEIGHTS.time + WEIGHTS.cost;
  } else {
    const sec = Math.max(0, (Date.parse(s.quote.sent_at) - Date.parse(s.received_at)) / 1000);
    // Time: full inside 2:00, linear to zero at 6:00 (same limits as the Dashboard).
    p.time = WEIGHTS.time * clamp01((RESPONSE_ZERO_S - sec) / (RESPONSE_ZERO_S - RESPONSE_FULL_S));
    if (p.time < WEIGHTS.time) leaks.late = WEIGHTS.time - p.time;
    // Accuracy: the customer saying yes is our best stand-in for "within 5 % of the best price".
    // Open quotes count half until they resolve; lost/expired count zero.
    const acc = s.outcome === "won" ? 1 : s.outcome === "open" ? 0.5 : 0;
    p.accuracy = WEIGHTS.accuracy * acc;
    if (acc < 1 && s.outcome !== "open") leaks.lost = WEIGHTS.accuracy * (1 - acc);
    // Cost: zero at $0.10 of LLM spend per quote.
    p.cost = WEIGHTS.cost * clamp01(1 - s.llm_cost_usd / COST_CAP_USD);
    if (p.cost < WEIGHTS.cost) leaks.cost = WEIGHTS.cost - p.cost;
  }
  if (s.booking && s.status_updates.length) p.tracking = WEIGHTS.tracking;
  const total = PARTS.reduce((a, k) => a + p[k], 0);
  return { session: s, points: p, total, leaks };
}

export function scoreboard(sessions: Session[], now = Date.now()) {
  const byRound = new Map<number, SessionScore[]>();
  for (const s of sessions) {
    const r = roundOf(s.received_at);
    byRound.set(r, [...(byRound.get(r) ?? []), scoreSession(s)]);
  }
  const first = Math.min(...byRound.keys());
  const rounds: RoundScore[] = [...byRound.entries()]
    .sort(([a], [b]) => a - b)
    .map(([round, list]) => {
      const points = zero();
      for (const x of list) for (const k of PARTS) points[k] += x.points[k];
      return { round, n: round - first + 1, start: roundStart(round), sessions: list, points, total: PARTS.reduce((a, k) => a + points[k], 0) };
    });
  const total = rounds.reduce((a, r) => a + r.total, 0);
  const leaks: Record<Leak, number> = { late: 0, unquoted: 0, lost: 0, cost: 0 };
  for (const r of rounds) for (const x of r.sessions) for (const [k, v] of Object.entries(x.leaks)) leaks[k as Leak] += v ?? 0;
  const max = sessions.length * (WEIGHTS.accuracy + WEIGHTS.time + WEIGHTS.cost);
  // "Last round" means the last finished one: the round still running has not had its 6 minutes yet.
  const done = rounds.filter((r) => Date.parse(r.start) + ROUND_S * 1000 <= now);
  const last = done.at(-1) ?? null;
  const prev = done.at(-2) ?? null;
  const best = rounds.reduce<RoundScore | null>((b, r) => (!b || r.total > b.total ? r : b), null);
  return { rounds, total, leaks, max, last, prev, best, avg: rounds.length ? total / rounds.length : null };
}
