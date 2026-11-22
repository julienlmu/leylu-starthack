// Command UI prototype: everything it shows, derived from the shared Session/Event shapes (lib/types.ts).
// Read-only helpers; the data itself comes from lib/live.ts like the main Sessions UI.
import { airOptions, mailOf, pieceCount, responseSeconds, totalWeight, type Mail } from "@/lib/format";
import { RESPONSE_FULL_S } from "@/lib/metrics";
import type { Event, PriceOption, Session } from "@/lib/types";

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

// ---- prices & airlines page (derived, read-only) ----
export function rates(list: Session[], events: Event[]) {
  const sources = new Map<string, number>(); // source label → requests it priced
  const airlines = new Map<string, { carrier: string; last: Option; lane: string; quoted: number }>();
  for (const s of [...list].sort((a, b) => Date.parse(a.received_at) - Date.parse(b.received_at))) {
    if (!s.rfq) continue;
    const p = priced(s, events);
    for (const src of new Set(p.options.map((o) => sourceOf(o, p.remembered)))) sources.set(src, (sources.get(src) ?? 0) + 1);
    for (const o of p.options) {
      const prev = airlines.get(o.carrier);
      airlines.set(o.carrier, { carrier: o.carrier, last: o, lane: route(s), quoted: (prev?.quoted ?? 0) + (isChosen(o, s.quote) ? 1 : 0) });
    }
  }
  return { sources, airlines: [...airlines.values()].sort((a, b) => b.quoted - a.quoted || a.carrier.localeCompare(b.carrier)) };
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
