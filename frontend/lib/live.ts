"use client";
// Live data for the Sessions UI (F2).
// Live backend: load the sessions, then apply every Event from the SSE stream (GET /api/stream) and re-fetch the
// session it belongs to. Event history is fetched per session on demand (loadEvents). A watchdog notices a dead
// backend; after the stream comes back, everything loaded is fetched again, so nothing missed stays missing.
// Mock mode: replay a scripted RFQ so the demo still moves.
import { useEffect, useMemo, useRef, useState } from "react";
import { loadData, loadEvents as fetchEvents, loadSession, type Data } from "./api";
import type { Event, PriceOption, Session } from "./types";

export type LiveData = Data & {
  connected: boolean; // live: SSE open · mock: replay running
  since: number; // ms timestamp when the page started listening; events after it are "new"
  // Apply a change locally (mock mode, or optimistic UI). Live mode also gets it back from the stream.
  apply: (event: Event, session?: Session) => void;
  // Put one session as the backend returned it (e.g. the reply of POST /intervene).
  applySession: (session: Session) => void;
  // Make sure a session's event history is loaded (live mode; mock data already has it). Cached per session.
  loadEvents: (sessionId: number) => void;
};

type State = Data & { connected: boolean; since: number };

const upsert = (sessions: Session[], s: Session) =>
  sessions.some((x) => x.id === s.id) ? sessions.map((x) => (x.id === s.id ? s : x)) : [s, ...sessions];

// History is authoritative up to its last event; keep stream events that arrived after it.
const mergeHistory = (events: Event[], sessionId: number, history: Event[]) => {
  const last = Math.max(0, ...history.map((e) => Date.parse(e.at)));
  return [
    ...events.filter((e) => e.session_id !== sessionId),
    ...history,
    ...events.filter((e) => e.session_id === sessionId && Date.parse(e.at) > last),
  ];
};

export function useLiveData(): LiveData | null {
  const [state, setState] = useState<State | null>(null);
  const loaded = useRef(new Set<number>()); // sessions whose history is loaded or loading
  const live = useRef(false);

  const actions = useMemo(() => {
    const apply = (event: Event, session?: Session) =>
      setState((d) => d && { ...d, events: [...d.events, event], sessions: session ? upsert(d.sessions, session) : d.sessions });
    const applySession = (session: Session) => setState((d) => d && { ...d, sessions: upsert(d.sessions, session) });
    const refreshEvents = (id: number) =>
      fetchEvents(id)
        .then((history) => setState((d) => d && { ...d, events: mergeHistory(d.events, id, history) }))
        .catch(() => loaded.current.delete(id)); // try again next time it is needed
    const loadEvents = (id: number) => {
      if (!live.current || loaded.current.has(id)) return;
      loaded.current.add(id);
      refreshEvents(id);
    };
    return { apply, applySession, refreshEvents, loadEvents };
  }, []);

  useEffect(() => {
    let stop = () => {};
    let cancelled = false;

    loadData().then((initial) => {
      if (cancelled) return;
      live.current = initial.live;
      setState({ ...initial, connected: false, since: Date.now() });

      if (initial.live) {
        let es: EventSource | null = null;
        let dropped = false;
        const resync = () => {
          loadData().then((fresh) => fresh.live && setState((d) => d && { ...d, sessions: fresh.sessions }));
          loaded.current.forEach((id) => actions.refreshEvents(id));
        };
        const markDown = () => {
          dropped = true;
          setState((d) => d && { ...d, connected: false });
        };
        const connect = () => {
          es = new EventSource("/api/stream");
          es.onopen = () => {
            setState((d) => d && { ...d, connected: true });
            if (dropped) {
              dropped = false; // back after a drop: fetch what the page holds again
              resync();
            }
          };
          es.onerror = markDown; // EventSource retries by itself
          es.onmessage = async (m) => {
            const event: Event = JSON.parse(m.data);
            actions.apply(event);
            if (event.session_id === null) return; // e.g. tariff_ingested: no session to refresh
            const session = await loadSession(event.session_id).catch(() => null);
            if (session) actions.applySession(session);
          };
        };
        connect();

        // Watchdog. The Next proxy keeps the browser's stream open when the backend dies, so EventSource never
        // errors and the badge would say Live forever. Every 20 s the session list is fetched: failing marks the
        // stream down and drops the dead connection; succeeding refreshes the list, and reopens the stream if needed.
        const watchdog = setInterval(async () => {
          const ok = await fetch("/api/sessions", { cache: "no-store" })
            .then(async (r) => {
              if (!r.ok) return false;
              const sessions: Session[] = await r.json();
              setState((d) => d && { ...d, sessions });
              return true;
            })
            .catch(() => false);
          if (!ok) {
            es?.close();
            es = null;
            markDown();
          } else if (!es) connect(); // onopen resyncs events
        }, 20_000);

        stop = () => {
          clearInterval(watchdog);
          es?.close();
        };
      } else {
        setState((d) => d && { ...d, connected: true });
        stop = replay(actions.apply);
      }
    });

    return () => {
      cancelled = true;
      stop();
    };
  }, [actions]);

  return useMemo(
    () => state && { ...state, apply: actions.apply, applySession: actions.applySession, loadEvents: actions.loadEvents },
    [state, actions],
  );
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
