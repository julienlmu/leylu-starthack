"use client";
// Live data for the Sessions UI (F2).
// Live backend: load once, then apply every Event from the SSE stream (GET /api/stream) and
// re-fetch the session it belongs to. Mock mode: replay a scripted RFQ so the demo still moves.
import { useEffect, useState } from "react";
import { loadData, type Data } from "./api";
import type { Event, PriceOption, Session } from "./types";

export type LiveData = Data & {
  connected: boolean; // live: SSE open · mock: replay running
  since: number; // ms timestamp when the page started listening; events after it are "new"
  // Apply a change locally (mock mode, or optimistic UI). Live mode also gets it back from the stream.
  apply: (event: Event, session?: Session) => void;
};

const upsert = (sessions: Session[], s: Session) =>
  sessions.some((x) => x.id === s.id) ? sessions.map((x) => (x.id === s.id ? s : x)) : [s, ...sessions];

export function useLiveData(): LiveData | null {
  const [data, setData] = useState<LiveData | null>(null);

  useEffect(() => {
    let stop = () => {};
    let cancelled = false;

    const apply = (event: Event, session?: Session) =>
      setData((d) =>
        d && {
          ...d,
          events: [...d.events, event],
          sessions: session ? upsert(d.sessions, session) : d.sessions,
        },
      );

    loadData().then((initial) => {
      if (cancelled) return;
      setData({ ...initial, connected: false, since: Date.now(), apply });

      if (initial.live) {
        const es = new EventSource("/api/stream");
        es.onopen = () => setData((d) => d && { ...d, connected: true });
        es.onerror = () => setData((d) => d && { ...d, connected: false }); // EventSource reconnects by itself
        es.onmessage = async (m) => {
          const event: Event = JSON.parse(m.data);
          apply(event);
          const session = await fetch(`/api/sessions/${event.session_id}`, { cache: "no-store" })
            .then((r) => (r.ok ? (r.json() as Promise<Session>) : null))
            .catch(() => null);
          if (session) setData((d) => d && { ...d, sessions: upsert(d.sessions, session) });
        };
        stop = () => es.close();
      } else {
        setData((d) => d && { ...d, connected: true });
        stop = replay(apply);
      }
    });

    return () => {
      cancelled = true;
      stop();
    };
  }, []);

  return data;
}

// ---- Mock replay: one RFQ going from mail to quote, repeated with a new session id ----

const iso = () => new Date().toISOString();

function replay(apply: (e: Event, s?: Session) => void): () => void {
  const timers: ReturnType<typeof setTimeout>[] = [];
  let run = 0;

  const start = () => {
    const id = 900 + run++;
    const ev = (kind: Event["kind"], text: string, data: Record<string, unknown> = {}, llm_cost_usd = 0): Event => ({
      session_id: id, at: iso(), kind, text, data, llm_cost_usd,
    });
    let s: Session = {
      id, customer: "Atelier Lumière", thread_id: `th-${id}`, received_at: iso(),
      stage: "new", outcome: "open", rfq: null, bids: [], quote: null, booking: null,
      status_updates: [], llm_cost_usd: 0, needs_human: false, paused: false,
    };
    const option = (o: Pick<PriceOption, "source" | "carrier" | "total" | "transit_days" | "rate_id">): PriceOption => ({
      currency: "EUR", valid_until: iso(), chargeable_weight_kg: 66, breakdown: [], ...o,
    });
    const best = option({ source: "carrier_bid", carrier: "Air France KLM Cargo", rate_id: "R-90412", total: 286.4, transit_days: 1 });

    const steps: [number, () => void][] = [
      [0, () => apply(ev("mail_in", "RFQ from Atelier Lumière", {
        from: "claire@atelier-lumiere.fr", to: "quotes@leylu.air", subject: "Devis fret aérien CDG → YUL",
        body: "Bonjour,\n\nPouvez-vous me faire un devis pour 2 colis 50x50x60 cm, 22 kg chacun, de Paris CDG à Montréal ? Le plus rapide possible.\n\nMerci,\nClaire",
      }), s)],
      [1500, () => apply(ev("routed", "Routed: customer RFQ (new thread)"))],
      [3000, () => {
        s = { ...s, stage: "pricing", llm_cost_usd: 0.00017, rfq: {
          origin: "CDG", destination: "YUL", ask: "fastest", pickup: null, ready_date: iso().slice(0, 10),
          pieces: [{ count: 2, length_cm: 50, width_cm: 50, height_cm: 60, weight_kg: 22 }],
          commodity: "lighting fixtures", dangerous_goods: false, customer_reference: null, language: "fr",
        } };
        apply(ev("extracted", "Extracted: CDG → YUL, 2 pcs, 66 kg chargeable, fastest", {}, 0.00017), s);
      }],
      [5000, () => {
        s = { ...s, bids: [
          option({ source: "sheet", carrier: "Air Transat Cargo", rate_id: null, total: 254.1, transit_days: 2 }),
          option({ source: "portal", carrier: "Air Canada Cargo", rate_id: "R-90398", total: 279.0, transit_days: 2 }),
        ] };
        apply(ev("priced", "Sheet + portal ready: best EUR 254.10 (Air Transat, 2 days)"), s);
      }],
      [6000, () => apply(ev("carrier_asked", "Asked 3 carriers for bids"))],
      [9000, () => apply(ev("bid", "Bid: Air France KLM Cargo EUR 286.40, 1 day"))],
      [11000, () => apply(ev("bid", "Cut-off: 2 of 3 answered in time"))],
      [13000, () => {
        s = { ...s, stage: "quoted", bids: [...s.bids, best], quote: { ...best, sent_at: iso() } };
        apply(ev("quote_sent", "Quote sent: EUR 286.40 all-in (fastest)", {
          from: "quotes@leylu.air", to: "claire@atelier-lumiere.fr", subject: "Re: Devis fret aérien CDG → YUL",
          body: "Bonjour Claire,\n\nMerci pour votre demande. L'option la plus rapide pour vos 2 colis CDG → Montréal est Air France KLM Cargo, 1 jour de transit.\n\nPrix total tout compris : 286,40 EUR.\n\nRépondez simplement à ce mail et nous réservons tout de suite.\n\nBien cordialement,\nL'équipe Leylü",
        }), s);
      }],
      [45000, start], // next demo RFQ
    ];
    for (const [ms, fn] of steps) timers.push(setTimeout(fn, ms));
  };

  timers.push(setTimeout(start, 2000));
  return () => timers.forEach(clearTimeout);
}
