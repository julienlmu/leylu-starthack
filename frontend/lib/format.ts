import type { Outcome, Session, Stage } from "./types";

export const money = (amount: number, currency: string) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency }).format(amount);

export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { timeZone: "Europe/Berlin", hour12: false });

// Seconds from the RFQ arriving to our quote going out (scored: full ≤ 120 s, zero at 360 s).
export const responseSeconds = (s: Session) =>
  s.quote ? Math.round((Date.parse(s.quote.sent_at) - Date.parse(s.received_at)) / 1000) : null;

export const duration = (sec: number) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;

export const usd = (v: number) => `$${v.toFixed(5)}`;

export const stageStyle: Record<Stage, string> = {
  new: "bg-sky-100 text-sky-800",
  pricing: "bg-amber-100 text-amber-800",
  quoted: "bg-violet-100 text-violet-800",
  booked: "bg-emerald-100 text-emerald-800",
  tracking: "bg-teal-100 text-teal-800",
  done: "bg-neutral-200 text-neutral-700",
  failed: "bg-red-100 text-red-800",
};

export const outcomeStyle: Record<Outcome, string> = {
  open: "text-neutral-500",
  won: "text-emerald-700",
  lost: "text-red-700",
  expired: "text-red-700",
};
