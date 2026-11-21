import type { Event, EventKind, Outcome, PriceOption, Session, Stage } from "./types";

export const money = (amount: number, currency: string) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(amount);

// Whole units for list strips, where a cent column only adds noise.
export const moneyShort = (amount: number, currency: string) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency, maximumFractionDigits: 0 }).format(amount);

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { timeZone: "Europe/Berlin", hour12: false });

export const clockShort = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { timeZone: "Europe/Berlin", hour12: false, hour: "2-digit", minute: "2-digit" });

export const day = (isoDate: string) =>
  new Date(isoDate).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });

// Seconds from the RFQ arriving to our quote going out (scored: full ≤ 120 s, zero at 360 s).
export const responseSeconds = (s: Session) =>
  s.quote ? Math.round((Date.parse(s.quote.sent_at) - Date.parse(s.received_at)) / 1000) : null;

export const TARGET_SECONDS = 120;
export const ZERO_SECONDS = 360;
export const COST_ZERO_USD = 0.1;

export type Pace = "on-target" | "late" | "zero";
export const pace = (sec: number): Pace => (sec <= TARGET_SECONDS ? "on-target" : sec < ZERO_SECONDS ? "late" : "zero");

export const duration = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.max(0, sec) % 60).padStart(2, "0")}`;

export const usd = (v: number) => `$${v.toFixed(5)}`;

export const offset = (fromIso: string, toIso: string) => {
  const sec = Math.round((Date.parse(toIso) - Date.parse(fromIso)) / 1000);
  return `+${duration(sec)}`;
};

export const STAGES: Stage[] = ["new", "pricing", "quoted", "booked", "tracking", "done", "failed"];
// The happy path a session walks; "failed" leaves it.
export const TRACK: Stage[] = ["new", "pricing", "quoted", "booked", "tracking", "done"];

export const stageLabel: Record<Stage, string> = {
  new: "New",
  pricing: "Pricing",
  quoted: "Quoted",
  booked: "Booked",
  tracking: "Tracking",
  done: "Done",
  failed: "Failed",
};

export const outcomeLabel: Record<Outcome, string> = {
  open: "Open",
  won: "Won",
  lost: "Lost",
  expired: "Expired",
};

export const kindLabel: Record<EventKind, string> = {
  mail_in: "Mail in",
  routed: "Routed",
  extracted: "Extracted",
  priced: "Priced",
  carrier_asked: "Carriers asked",
  bid: "Bid",
  quote_sent: "Quote sent",
  accepted: "Accepted",
  declined: "Declined",
  booked: "Booked",
  status_sent: "Status sent",
  tracking_answer: "Tracking answer",
  tariff_ingested: "Tariff ingested",
  needs_human: "Needs a person",
  intervened: "Person stepped in",
  error: "Error",
};

// Fixed magnitude ramp for timeline marks: what the customer sees is largest.
export type Magnitude = "mail" | "decision" | "step" | "alert";
export const magnitude: Record<EventKind, Magnitude> = {
  mail_in: "mail",
  quote_sent: "mail",
  accepted: "mail",
  declined: "mail",
  status_sent: "mail",
  tracking_answer: "mail",
  priced: "decision",
  booked: "decision",
  extracted: "decision",
  bid: "step",
  routed: "step",
  carrier_asked: "step",
  tariff_ingested: "step",
  intervened: "step",
  needs_human: "alert",
  error: "alert",
};

// "Emirates SkyCargo" → "Emirates", "Air France KLM Cargo" → "Air France KLM".
export const shortCarrier = (carrier: string) => carrier.replace(/\s*(Sky)?Cargo$/i, "") || carrier;

export const sourceLabel: Record<PriceOption["source"], string> = {
  sheet: "Rate sheet",
  portal: "Portal",
  carrier_bid: "Carrier bid",
};

export type Mail = { from: string; to: string; subject: string; body: string };
export const mailOf = (e: Event): Mail | null => {
  const d = e.data as Partial<Record<keyof Mail, unknown>>;
  return typeof d.body === "string"
    ? { from: String(d.from ?? ""), to: String(d.to ?? ""), subject: String(d.subject ?? ""), body: d.body }
    : null;
};

export const isOurs = (m: Mail) => m.from.endsWith("@leylu.air");

// Ways to fly it vs trucker pickup legs: only air options compete on price and speed.
export const airOptions = (bids: PriceOption[]) => bids.filter((b) => b.leg !== "pickup");
export const pickupLegs = (bids: PriceOption[]) => bids.filter((b) => b.leg === "pickup");

export const sameOption = (a: PriceOption, b: PriceOption) =>
  a.carrier === b.carrier && a.source === b.source && a.total === b.total && a.rate_id === b.rate_id;

export const totalWeight = (s: Session) => s.rfq?.pieces.reduce((sum, p) => sum + p.count * p.weight_kg, 0) ?? 0;
export const pieceCount = (s: Session) => s.rfq?.pieces.reduce((sum, p) => sum + p.count, 0) ?? 0;

// Free-text search over everything an operator might type: customer, route, reference, #id, carrier, booking ref.
export const matches = (s: Session, q: string) => {
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  // "#17" must not also match "#170"; a bare number matches the id exactly or any text.
  const exactId = words.find((w) => /^#\d+$/.test(w));
  if (exactId && exactId !== `#${s.id}`) return false;
  const hay = [
    `#${s.id}`,
    s.customer,
    s.thread_id,
    s.rfq?.origin,
    s.rfq?.destination,
    s.rfq ? `${s.rfq.origin}-${s.rfq.destination} ${s.rfq.origin}→${s.rfq.destination}` : "",
    s.rfq?.customer_reference,
    s.rfq?.commodity,
    s.quote?.carrier,
    s.quote?.rate_id,
    ...s.bids.map((b) => b.carrier),
    s.booking?.confirmation,
    s.booking?.booking_reference,
    s.booking?.rate_id,
    s.booking?.airline,
  ]
    .join(" ")
    .toLowerCase();
  return words.every((w) => hay.includes(w));
};
