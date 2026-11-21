// Shapes from docs/PLAN.md §7 (copied into docs/CONTRACT.md by the Lead). Keep them identical.

export type Ask = "cheapest" | "fastest";

export type Piece = {
  count: number;
  length_cm: number;
  width_cm: number;
  height_cm: number;
  weight_kg: number; // per piece
};

export type Rfq = {
  origin: string;
  destination: string;
  ask: Ask;
  pickup: { address: string; zone: string | null } | null; // null = airport delivery
  ready_date: string;
  pieces: Piece[];
  volume_m3?: number | null; // proposed by Julien (A3) for RFQs that give a volume
  commodity: string;
  dangerous_goods: boolean;
  customer_reference: string | null;
  language: string;
};

export type PriceOption = {
  source: "sheet" | "portal" | "carrier_bid";
  carrier: string;
  rate_id: string | null;
  currency: string;
  total: number;
  transit_days: number;
  valid_until: string;
  chargeable_weight_kg: number;
  breakdown: { label: string; amount: number }[];
};

export type Stage = "new" | "pricing" | "quoted" | "booked" | "tracking" | "done" | "failed";
export type Outcome = "open" | "won" | "lost" | "expired";

export type Session = {
  id: number;
  customer: string;
  thread_id: string;
  received_at: string;
  stage: Stage;
  outcome: Outcome;
  rfq: Rfq | null;
  bids: PriceOption[];
  quote: (PriceOption & { sent_at: string }) | null;
  // PLAN.md §7 shape; booking_reference/airline/status come from the portal's BookingOut (Julien, A5) until CONTRACT.md settles it.
  booking: {
    rate_id: string;
    confirmation?: string;
    booked_at?: string;
    booking_reference?: string;
    airline?: string;
    status?: string;
  } | null;
  status_updates: { at: string; text: string }[];
  llm_cost_usd: number;
  needs_human: boolean;
  paused: boolean;
};

export type EventKind =
  | "mail_in"
  | "routed"
  | "extracted"
  | "priced"
  | "carrier_asked"
  | "bid"
  | "quote_sent"
  | "accepted"
  | "declined"
  | "booked"
  | "status_sent"
  | "tracking_answer"
  | "tariff_ingested"
  | "needs_human"
  | "intervened"
  | "error";

// Mail events (mail_in, quote_sent, status_sent, tracking_answer, intervened with send) carry
// data.from / data.to / data.subject / data.body so the UI can show the thread (CONTRACT.md, L2 proposal).
export type Event = {
  session_id: number | null; // null for events without a session (tariff_ingested)
  at: string;
  kind: EventKind;
  text: string;
  data: Record<string, unknown>;
  llm_cost_usd: number;
};
