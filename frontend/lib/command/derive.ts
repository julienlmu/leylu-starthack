// Command UI prototype: everything it shows, derived from the shared Session/Event shapes (lib/types.ts).
// Read-only helpers; the data itself comes from lib/live.ts like the main Sessions UI.
import { airOptions, day, mailOf, moneyShort, pieceCount, responseSeconds, totalWeight, type Mail } from "@/lib/format";
import { RESPONSE_FULL_S } from "@/lib/metrics";
import type { Event, PriceOption, Session } from "@/lib/types";
import { city } from "./cities";

// The three groups of the Requests list, in display order.
export type Group = "need" | "busy" | "done";
export const GROUP_ORDER: Record<Group, number> = { need: 0, busy: 1, done: 2 };

export function group(s: Session): Group {
  if (s.needs_human) return "need";
  if ((s.stage === "new" || s.stage === "pricing") && !s.quote) return "busy";
  return "done";
}

// Status badge: label + tone.
export function badge(s: Session): { label: string; tone: string } {
  const g = group(s);
  if (g === "need") return { label: "Needs you", tone: "b-bad" };
  if (g === "busy") return { label: "Pricing", tone: "b-info" };
  if (s.booking || s.outcome === "won") return { label: "Booked", tone: "b-good" };
  if (s.outcome === "lost") return { label: "Declined", tone: "b-muted" };
  if (s.outcome === "expired") return { label: "Expired", tone: "b-muted" };
  if (!s.quote) return { label: "No quote", tone: "b-muted" };
  return { label: "Quote sent", tone: "b-warn" };
}

export const route = (s: Session) => (s.rfq ? `${s.rfq.origin} → ${s.rfq.destination}` : "");

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter((w) => /^[A-Za-zÀ-ž]/.test(w))
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("") || "?";

// Short goods line for the table: "3 pcs · 1,720 kg".
export const cargo = (s: Session) => {
  if (!s.rfq) return "Reading the mail";
  const n = pieceCount(s);
  return `${n} ${n === 1 ? "pc" : "pcs"} · ${totalWeight(s).toLocaleString("en-GB")} kg`;
};

export const elapsed = (s: Session, now: number) => Math.max(0, Math.round((now - Date.parse(s.received_at)) / 1000));

// m:ss; an hour or more (a request stuck since yesterday) as "25h 48m" instead of "1548:24".
export const fmt = (sec: number) =>
  sec >= 3600
    ? `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`
    : `${Math.floor(sec / 60)}:${String(Math.max(0, sec) % 60).padStart(2, "0")}`;

// The "Answered" cell: "1:31", "running 0:48" or "waiting 2:41"; late over 2:00.
export function timing(s: Session, now: number): { text: string; late: boolean } {
  const sent = responseSeconds(s);
  if (sent !== null) return { text: fmt(sent), late: sent > RESPONSE_FULL_S };
  const g = group(s);
  if (g === "done") return { text: "—", late: false };
  const sec = elapsed(s, now);
  return { text: `${g === "busy" ? "running" : "waiting"} ${fmt(sec)}`, late: sec > RESPONSE_FULL_S };
}

const of = (events: Event[], id: number) => events.filter((e) => e.session_id === id);

// "n of m airlines answered" while pricing: m from the carrier_asked text ("Asked 4 carriers"), n = bid events.
export function progress(s: Session, events: Event[]) {
  const ev = of(events, s.id);
  const asked = Number(ev.find((e) => e.kind === "carrier_asked")?.text.match(/Asked (\d+)/)?.[1] ?? 0);
  const answered = ev.filter((e) => e.kind === "bid" && !/^Cut-off/i.test(e.text)).length;
  if (!asked) return { pct: s.rfq ? 15 : 5, text: s.rfq ? "checking price lists and the portal" : "reading the mail" };
  return { pct: Math.min(100, Math.round((answered / asked) * 100)), text: `${Math.min(answered, asked)} of ${asked} airlines answered` };
}

// Why a person is needed: the latest needs_human event, else a generic line.
export const reason = (s: Session, events: Event[]) =>
  of(events, s.id).filter((e) => e.kind === "needs_human").at(-1)?.text ?? "The assistant handed this request to a person.";

// ---- the thread ----
export type ThreadMsg = { at: string; ours: boolean; mail: Mail };
const CUSTOMER_KINDS: Event["kind"][] = ["mail_in", "accepted", "declined"];

export const thread = (events: Event[], id: number): ThreadMsg[] =>
  of(events, id)
    .map((e) => ({ e, mail: mailOf(e) }))
    .filter((x): x is { e: Event; mail: Mail } => x.mail !== null)
    .map(({ e, mail }) => ({ at: e.at, ours: !CUSTOMER_KINDS.includes(e.kind), mail }));

export const gateNotes = (events: Event[], id: number) =>
  of(events, id).filter((e) => e.kind === "routed" && e.text.startsWith("Quote gate"));

// ---- prices ----
export type Option = PriceOption & { portal_form?: unknown };
export type Priced = { options: Option[]; chosen: Option | null; remembered: boolean };

const same = (a: PriceOption, b: PriceOption) =>
  a.carrier === b.carrier && a.source === b.source && a.total === b.total && (a.rate_id ?? null) === (b.rate_id ?? null);

// Price options from the latest priced event that carries them (the /api/price response), else the session's bids.
export function priced(s: Session, events: Event[]): Priced {
  const latest = of(events, s.id)
    .filter((e) => e.kind === "priced" && Array.isArray(e.data.options))
    .at(-1);
  if (latest) {
    const options = airOptions(latest.data.options as Option[]).sort((a, b) => a.total - b.total);
    return { options, chosen: (latest.data.chosen as Option | null) ?? null, remembered: /REMEMBERED/.test(`${latest.text} ${latest.data.why ?? ""}`) };
  }
  const options: Option[] = airOptions(s.bids);
  if (s.quote && !options.some((o) => same(o, s.quote!))) options.push(s.quote);
  return { options: options.sort((a, b) => a.total - b.total), chosen: s.quote, remembered: false };
}

export const isChosen = (o: PriceOption, chosen: PriceOption | null) => !!chosen && same(o, chosen);

export function sourceOf(o: Option, remembered: boolean) {
  if (o.portal_form) return "Web form";
  if (o.source === "portal") return remembered ? "Remembered" : "Portal";
  return o.source === "sheet" ? "Sheet" : "Bid";
}

// The newest request being priced right now (the slim strip on Requests), else null.
export const pricingNow = (list: Session[]) =>
  list.filter((s) => group(s) === "busy").sort((a, b) => Date.parse(b.received_at) - Date.parse(a.received_at))[0] ?? null;

// The 5-step timeline with times. Monotonic: a later step done means the earlier ones are done too
// (a sheet-only quote never asks carriers).
export function steps(s: Session, events: Event[]): { label: string; state: "ok" | "cur" | "todo"; note: string }[] {
  const ev = of(events, s.id);
  const first = (pred: (e: Event) => boolean) => ev.find(pred);
  const at = (e?: { at: string }) => (e ? fmt(Math.max(0, Math.round((Date.parse(e.at) - Date.parse(s.received_at)) / 1000))) : "");
  const asked = first((e) => e.kind === "carrier_asked");
  const n = asked?.text.match(/Asked (\d+)/)?.[1];
  const sent = first((e) => e.kind === "quote_sent") ?? (s.quote ? { at: s.quote.sent_at } : undefined);
  const raw: [string, { at: string } | undefined, string][] = [
    ["Mail read", first((e) => e.kind === "extracted"), ""],
    ["Airlines asked", asked, n ? ` · ${n} airlines` : ""],
    ["Prices coming in", first((e) => e.kind === "priced"), ""],
    ["Quote checked", first((e) => e.kind === "routed" && e.text.startsWith("Quote gate")), ""],
    ["Reply sent", sent, ""],
  ];
  const last = raw.map((r) => !!r[1]).lastIndexOf(true);
  const now = progress(s, events);
  return raw.map(([label, e, extra], i) => ({
    label,
    state: i <= last ? "ok" : i === last + 1 ? "cur" : "todo",
    note: i <= last ? (e ? `${at(e)}${extra}` : "done") : i === last + 1 ? now.text : "pending",
  }));
}

// ---- sent quotes, bookings, tracking pages ----
export const cityRoute = (s: Session) => (s.rfq ? `${city(s.rfq.origin)} → ${city(s.rfq.destination)}` : "");

// "just now", "12 min ago", "3 h ago", "2 d ago".
export function ago(iso: string, now: number) {
  const min = Math.floor((now - Date.parse(iso)) / 60000);
  if (!Number.isFinite(min)) return "";
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  return min < 1440 ? `${Math.floor(min / 60)} h ago` : `${Math.floor(min / 1440)} d ago`;
}

export type Answer = "waiting" | "accepted" | "declined" | "expired";
export const answerOf = (s: Session): Answer =>
  s.booking || s.outcome === "won" ? "accepted" : s.outcome === "lost" ? "declined" : s.outcome === "expired" ? "expired" : "waiting";
export const ANSWER: Record<Answer, [string, string]> = {
  waiting: ["Waiting", "b-warn"], accepted: ["Accepted", "b-good"], declined: ["Declined", "b-muted"], expired: ["Expired", "b-muted"],
};

// What our texts say happened to a booking (airline confirmations, booking_agent.UPDATE_EVENTS wording).
const CONFIRMED = /\bconfirmed\b|bestätigt/i;
const DEPARTED = /\bdeparted\b|\bairborne\b|wheels\s+up|abgeflogen/i;
const ARRIVED = /\barrived\b|\blanded\b|angekommen|gelandet/i;

export type Leg = { label: string; at: string | null; done: boolean };

// Booked → Airline confirmed → Departed → Arrived, from booking.status and status_updates. Monotonic: a later
// step seen means the earlier ones happened (their time stays unknown). Unknown steps stay not done.
export function legs(s: Session): Leg[] {
  const b = s.booking;
  const ups = s.status_updates.filter((u) => !/cancel/i.test(u.text));
  const hit = (re: RegExp) => ups.find((u) => re.test(u.text))?.at ?? null;
  const raw: [string, string | null, boolean][] = [
    ["Booked", b?.booked_at ?? null, !!b],
    ["Airline confirmed", hit(CONFIRMED), b?.status === "confirmed" || !!hit(CONFIRMED)],
    ["Departed", hit(DEPARTED), !!hit(DEPARTED)],
    ["Arrived", hit(ARRIVED), !!hit(ARRIVED)],
  ];
  const last = raw.map((r) => r[2]).lastIndexOf(true);
  return raw.map(([label, at], i) => ({ label, at, done: i <= last }));
}

export const cancelled = (s: Session) => s.booking?.status === "cancelled";

export function bookingBadge(s: Session): { label: string; tone: string } {
  if (cancelled(s)) return { label: "Cancelled", tone: "b-bad" };
  const l = legs(s);
  if (l[3].done) return { label: "Arrived", tone: "b-good" };
  if (l[2].done) return { label: "In the air", tone: "b-info" };
  if (l[1].done) return { label: "Confirmed", tone: "b-good" };
  return { label: s.booking?.status && s.booking.status !== "confirmed" ? s.booking.status : "Waiting for the airline", tone: "b-warn" };
}

// AWB and flight number as our own texts name them ("AWB 160-48213377", "CX 288", "volo EK 092"); null if none.
export function awbFlight(s: Session, events: Event[]) {
  const ours = of(events, s.id).filter((e) => e.kind === "booked" || e.kind === "status_sent" || e.kind === "tracking_answer");
  const text = [s.booking?.confirmation ?? "", ...s.status_updates.map((u) => u.text), ...ours.map((e) => `${e.text}\n${mailOf(e)?.body ?? ""}`)].join("\n");
  const awb = text.match(/\bAWB\s*(\d{3}-?\d{8})\b/)?.[1] ?? s.booking?.confirmation?.match(/^\d{3}-?\d{8}$/)?.[0] ?? null;
  // shortcut: a two-character airline code + 3-4 digits; a reference written like that would read as a flight.
  const flight = text.match(/\b([A-Z]{2}|[A-Z]\d|\d[A-Z]) ?(\d{3,4})\b(?!-)/);
  return { awb, flight: flight ? `${flight[1]} ${flight[2]}` : null };
}

// Tracking on one booked shipment: our answers (tracking_answer), each with the customer mail before it if the
// thread has one, and whether a customer mail after the booking still has no reply and was not routed.
export function trackingOf(s: Session, events: Event[]) {
  const ev = of(events, s.id);
  const msgs = thread(events, s.id);
  const booked = Date.parse(s.booking?.booked_at ?? ev.find((e) => e.kind === "booked")?.at ?? "");
  const answers = ev.filter((e) => e.kind === "tracking_answer").map((a) => {
    const q = msgs.filter((m) => !m.ours && Date.parse(m.at) > booked && Date.parse(m.at) <= Date.parse(a.at)).at(-1) ?? null;
    return { a, reply: mailOf(a), q, sec: q ? Math.max(0, Math.round((Date.parse(a.at) - Date.parse(q.at)) / 1000)) : null };
  });
  const lastIn = ev.filter((e) => e.kind === "mail_in" && Date.parse(e.at) > booked).at(-1);
  const handled = lastIn && ev.some((e) => Date.parse(e.at) > Date.parse(lastIn.at) && ["tracking_answer", "status_sent", "intervened", "routed"].includes(e.kind));
  const waiting = lastIn && !handled ? { at: lastIn.at, mail: mailOf(lastIn) } : null;
  const newest = Math.max(0, ...[waiting?.at, answers.at(-1)?.q?.at, answers.at(-1)?.a.at].map((x) => Date.parse(x ?? "") || 0));
  return { answers, waiting, newest: newest || null };
}

// ---- sent quotes board ----
// Sent → answered (the customer said yes or no) → accepted.
export function funnel(quoted: Session[]) {
  const n = (a: Answer) => quoted.filter((s) => answerOf(s) === a).length;
  return { sent: quoted.length, answered: n("accepted") + n("declined"), accepted: n("accepted") };
}

// Summed all-in per currency ("€12,400 + $3,100"); currencies are never converted.
export function sums(list: Session[]) {
  const m = new Map<string, number>();
  for (const s of list) if (s.quote) m.set(s.quote.currency, (m.get(s.quote.currency) ?? 0) + s.quote.total);
  return [...m].map(([c, v]) => moneyShort(v, c)).join(" + ");
}

// ---- bookings schedule ----
export const DAY_MS = 86_400_000;
const midnight = (t: number) => new Date(t).setHours(0, 0, 0, 0);

// A booking on the day scale: start = the ready date (local midnight); end = start + quoted transit days, null if unknown.
export type Slot = { s: Session; start: number; end: number | null };
export type DayGroup = { key: string; label: string; rows: Slot[]; from: number; to: number };

// Bookings grouped by ready date: Today, Tomorrow, each later day, then Earlier; no readable date → unscheduled.
export function schedule(list: Session[], now: number) {
  const today = midnight(now);
  const groups = new Map<string, DayGroup & { order: number }>();
  const unscheduled: Session[] = [];
  for (const s of list) {
    const start = s.rfq?.ready_date ? Date.parse(`${s.rfq.ready_date.slice(0, 10)}T00:00:00`) : NaN;
    if (!Number.isFinite(start)) {
      unscheduled.push(s);
      continue;
    }
    const days = s.quote?.transit_days;
    const end = typeof days === "number" && days > 0 ? start + days * DAY_MS : null;
    const diff = Math.round((start - today) / DAY_MS);
    const key = diff < 0 ? "earlier" : String(diff);
    const label = diff < 0 ? "Earlier" : diff === 0 ? "Today" : diff === 1 ? "Tomorrow" : day(new Date(start).toISOString());
    const g = groups.get(key) ?? { key, label, rows: [], from: start, to: start, order: diff < 0 ? 1e6 : diff };
    g.rows.push({ s, start, end });
    g.from = Math.min(g.from, start);
    g.to = Math.max(g.to, end ?? start + DAY_MS, g.from + DAY_MS);
    groups.set(key, g);
  }
  const out = [...groups.values()].sort((a, b) => a.order - b.order);
  for (const g of out) {
    g.to = midnight(g.to + DAY_MS - 1); // whole days on the scale
    g.rows.sort((a, b) => a.start - b.start || a.s.customer.localeCompare(b.s.customer));
  }
  return { groups: out as DayGroup[], unscheduled };
}

// ---- prices & airlines (derived, read-only) ----
export const SOURCE_NAME: Record<string, string> = {
  Portal: "Portal", Sheet: "Price list", Bid: "Mail bid", Remembered: "Remembered", "Web form": "Web form",
};

// When a request was priced: its latest priced event, else the quote, else the mail.
export const pricedAt = (s: Session, events: Event[]) =>
  Date.parse(of(events, s.id).filter((e) => e.kind === "priced").at(-1)?.at ?? s.quote?.sent_at ?? s.received_at);

// Per-airline: which sources priced it, its newest price and where that came from.
export function airlines(list: Session[], events: Event[]) {
  const m = new Map<string, { carrier: string; sources: Set<string>; last: Option; s: Session; at: number }>();
  for (const s of list) {
    if (!s.rfq) continue;
    const p = priced(s, events);
    const at = pricedAt(s, events);
    for (const o of p.options) {
      const prev = m.get(o.carrier);
      const src = SOURCE_NAME[sourceOf(o, p.remembered)];
      if (!prev) m.set(o.carrier, { carrier: o.carrier, sources: new Set([src]), last: o, s, at });
      else {
        prev.sources.add(src);
        if (at >= prev.at) Object.assign(prev, { last: o, s, at });
      }
    }
  }
  return [...m.values()].sort((a, b) => b.at - a.at || a.carrier.localeCompare(b.carrier));
}

// The five price sources and what the event log says about each in the last 30 minutes.
// shortcut: status is read from event wording (503, 429, "down"); a real health endpoint would replace this.
export type SourceState = { name: string; what: string; status: "Down" | "Limited" | "Working" | "Idle"; note: string; last: number | null };
const WINDOW_MS = 30 * 60_000;
const DOWN = /\b50[0-4]\b|\bdown\b|unavailable|unreachable|timed? ?out/i;
const LIMITED = /\b429\b|rate.?limit/i;

export function sourceStates(list: Session[], events: Event[], now: number): SourceState[] {
  const uses: Record<string, number[]> = { Portal: [], Sheet: [], Bid: [], Remembered: [], Desk: [] };
  for (const s of list) {
    if (!s.rfq) continue;
    const p = priced(s, events);
    const at = pricedAt(s, events);
    for (const o of p.options) {
      const k = sourceOf(o, p.remembered);
      uses[k === "Web form" ? "Portal" : k]?.push(at);
    }
  }
  for (const e of events) {
    if (e.kind === "bid") uses.Bid.push(Date.parse(e.at));
    if (/rate ?desk/i.test(e.text)) uses.Desk.push(Date.parse(e.at));
  }
  const recent = events.filter((e) => now - Date.parse(e.at) <= WINDOW_MS);
  const trouble = (re: RegExp) => recent.filter((e) => re.test(e.text) && (DOWN.test(e.text) || LIMITED.test(e.text)));
  const defs: [string, string, string, Event[]][] = [
    ["Portal", "Live airline prices, booked by rate ID", "Portal", trouble(/portal/i)],
    ["Airline price lists", "Rate sheets loaded from the airlines", "Sheet", trouble(/sheet|price list|tariff/i)],
    ["Airlines by mail", "Asked on each request; answers within the bid window", "Bid", trouble(/carrier|bid/i)],
    ["Rate desk", "Asked when the portal is down", "Desk", trouble(/rate ?desk/i)],
    ["Portal memory", "Earlier portal prices reused while the portal is down", "Remembered", []],
  ];
  return defs.map(([name, what, k, bad]) => {
    const ts = uses[k].filter(Number.isFinite);
    const last = ts.length ? Math.max(...ts) : null;
    const worst = bad.find((e) => DOWN.test(e.text)) ?? bad[0];
    const code = worst?.text.match(/\b(5\d\d|429)\b/)?.[1];
    if (worst) {
      const n = bad.length;
      return { name, what, last, status: DOWN.test(worst.text) ? "Down" : "Limited", note: `${code ?? "Errors"}${n > 1 ? ` ×${n}` : ""} in the last 30 min` };
    }
    if (last !== null && now - last <= WINDOW_MS) return { name, what, last, status: "Working", note: "Priced a request in the last 30 min" };
    return { name, what, last, status: "Idle", note: last === null ? "Not used yet" : "No activity in the last 30 min" };
  });
}
