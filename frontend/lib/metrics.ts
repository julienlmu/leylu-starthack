// F4: CRM numbers, computed from sessions only (no extra endpoint needed).
import type { Outcome, Session } from "./types";

export const RESPONSE_FULL_S = 120; // full time points
export const RESPONSE_ZERO_S = 360; // zero time points, request lost
export const COST_CAP_USD = 0.1; // zero cost points per accepted quote

const secs = (s: Session) =>
  s.quote ? Math.max(0, Math.round((Date.parse(s.quote.sent_at) - Date.parse(s.received_at)) / 1000)) : null;

export function metrics(sessions: Session[]) {
  const quoted = sessions.filter((s) => s.quote).sort((a, b) => Date.parse(a.quote!.sent_at) - Date.parse(b.quote!.sent_at));
  const times = quoted.map(secs) as number[];
  const won = sessions.filter((s) => s.outcome === "won");
  const totalCost = sessions.reduce((sum, s) => sum + s.llm_cost_usd, 0);
  const outcomes: Record<Outcome, number> = { won: 0, open: 0, lost: 0, expired: 0 };
  for (const s of sessions) outcomes[s.outcome]++;

  return {
    sessions: sessions.length,
    quoted,
    quoteRate: sessions.length ? quoted.length / sessions.length : 0,
    won: won.length,
    booked: sessions.filter((s) => s.booking),
    outcomes,
    avgResponseS: times.length ? Math.round(times.reduce((a, b) => a + b, 0) / times.length) : null,
    within2minRate: times.length ? times.filter((t) => t <= RESPONSE_FULL_S).length / times.length : 0,
    responseSeconds: secs,
    totalCost,
    costPerQuote: quoted.length ? totalCost / quoted.length : null,
    costPerWon: won.length ? totalCost / won.length : null,
    needsHuman: sessions.filter((s) => s.needs_human).length,
  };
}
