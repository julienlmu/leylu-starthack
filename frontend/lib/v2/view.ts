// v2 proposal: view helpers on top of the existing lib (read-only reuse of types and format).
import { responseSeconds } from "@/lib/format";
import { RESPONSE_FULL_S, RESPONSE_ZERO_S } from "@/lib/metrics";
import type { Event, Outcome, Session } from "@/lib/types";

export const outcomeVar: Record<Outcome, string> = {
  won: "bg-(--v2-won) text-(--v2-won-ink)",
  open: "bg-(--v2-open) text-(--v2-open-ink)",
  lost: "bg-(--v2-lost) text-(--v2-lost-ink)",
  expired: "bg-(--v2-expired) text-(--v2-expired-ink)",
};

// LLM cost in US cents: "0.017¢" for a tiny call, "1.20¢" above a tenth of a cent.
export const cents = (usd: number) => {
  const c = usd * 100;
  return `${c < 0.1 ? c.toFixed(3) : c.toFixed(2)}¢`;
};

export type Pace = "ok" | "late" | "zero";
export const paceOf = (sec: number): Pace => (sec <= RESPONSE_FULL_S ? "ok" : sec < RESPONSE_ZERO_S ? "late" : "zero");
export const paceText: Record<Pace, string> = { ok: "within 2:00", late: "late, over 2:00", zero: "past 6:00, scores zero" };

// The round a jury follows: received → read → bids → priced → quoted → booked.
export type Step = { key: string; label: string; at: string | null; done: boolean };

export function steps(s: Session, events: Event[]): Step[] {
  const first = (...kinds: Event["kind"][]) => events.find((e) => kinds.includes(e.kind))?.at ?? null;
  const read = first("extracted");
  const bids = first("carrier_asked", "bid");
  const priced = first("priced");
  const booked = s.booking?.booked_at ?? first("booked");
  return [
    { key: "received", label: "Received", at: s.received_at, done: true },
    { key: "read", label: "Read", at: read, done: !!s.rfq || !!read },
    { key: "bids", label: "Bids", at: bids, done: !!bids || s.bids.some((b) => b.source === "carrier_bid") },
    { key: "priced", label: "Priced", at: priced, done: !!priced || s.bids.length > 0 },
    { key: "quoted", label: "Quoted", at: s.quote?.sent_at ?? null, done: !!s.quote },
    { key: "booked", label: "Booked", at: booked, done: !!s.booking },
  ];
}

// Seconds on the round's clock: the response time once quoted, else time since the mail came in.
export const roundSeconds = (s: Session, now: number) =>
  responseSeconds(s) ?? Math.max(0, Math.round((now - Date.parse(s.received_at)) / 1000));

// Gate findings ("routed" event "Quote gate: …" with data.findings) plus why a person is needed.
export type Note = { level: string; text: string; at: string };
export function notes(events: Event[]): Note[] {
  return events.flatMap((e): Note[] => {
    if (e.kind === "routed" && e.text.startsWith("Quote gate:")) {
      const f = Array.isArray(e.data.findings) ? (e.data.findings as { level?: string; text?: string }[]) : [];
      return f.length
        ? f.map((x) => ({ level: String(x.level ?? "note"), text: String(x.text ?? ""), at: e.at }))
        : [{ level: "note", text: e.text.replace(/^Quote gate:\s*/, ""), at: e.at }];
    }
    if (e.kind === "needs_human") return [{ level: "person", text: e.text, at: e.at }];
    if (e.kind === "error") return [{ level: "error", text: e.text, at: e.at }];
    return [];
  });
}
