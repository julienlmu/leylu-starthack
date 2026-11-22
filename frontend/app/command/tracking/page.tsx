"use client";
// Shipment tracking as a messenger: conversations with booked customers (left), the mail thread (middle) and the
// shipment's status (right). Narrow screens show the list, then the thread with a back button.
import { useEffect, useRef, useState } from "react";
import { Search, useDrawer, useEvents } from "@/components/command/bits";
import { useCommand, useNow } from "@/components/command/shell";
import { clockShort, day, matches, shortCarrier } from "@/lib/format";
import type { LiveData } from "@/lib/live";
import type { Session } from "@/lib/types";
import { city } from "@/lib/command/cities";
import { awbFlight, bookingBadge, legs, thread, trackingOf, type ThreadMsg } from "@/lib/command/derive";

type Item = { s: Session; msgs: ThreadMsg[]; waiting: boolean; last: number };
const dayKey = (iso: string) => new Date(iso).toDateString();
const firstLine = (t: string) => t.trim().split(/\n+/).find((l) => l.trim()) ?? "";

export default function Tracking() {
  const data = useCommand();
  const now = useNow();
  const { pick, drawer } = useDrawer(data, now);
  const [sel, setSel] = useState<number | null>(null);
  const [opened, setOpened] = useState(false); // narrow screens: the thread replaces the list
  const [q, setQ] = useState("");
  const booked = (data?.sessions ?? []).filter((s) => s.booking);
  useEvents(data, booked.map((s) => s.id));
  if (!data) return <p className="hint">Loading…</p>;

  const items: Item[] = booked
    .map((s) => {
      const msgs = thread(data.events, s.id);
      return { s, msgs, waiting: !!trackingOf(s, data.events).waiting, last: Date.parse(msgs.at(-1)?.at ?? s.booking!.booked_at ?? s.received_at) || 0 };
    })
    .sort((a, b) => Number(b.waiting) - Number(a.waiting) || b.last - a.last);
  if (!items.length) return <div className="card calm">No bookings yet. Conversations appear here once a customer has booked.</div>;
  const shown = items.filter((i) => !q || matches(i.s, q));
  const cur = items.find((i) => i.s.id === sel) ?? items[0];

  return (
    <div className={`msgr card${opened ? " opened" : ""}`}>
      <aside className="m-list" aria-label="Conversations">
        <div className="m-search"><Search value={q} onChange={setQ} label="Search customer, route or BK reference" /></div>
        <ul>
          {shown.map(({ s, msgs, waiting, last }) => {
            const m = msgs.at(-1);
            return (
              <li key={s.id}>
                <button type="button" aria-current={s.id === cur.s.id ? "true" : undefined} onClick={() => { setSel(s.id); setOpened(true); }}>
                  <span className="c-top">
                    <b>{s.customer}</b>
                    <small className="mono">{last ? clockShort(new Date(last).toISOString()) : ""}</small>
                  </span>
                  <span className="c-ref mono">{s.booking!.booking_reference ?? s.booking!.rate_id}</span>
                  <span className="c-prev">
                    <span>{m ? `${m.ours ? "Leylü: " : ""}${firstLine(m.mail.body)}` : "No mails stored"}</span>
                    {waiting && <i className="dot" title="Waiting for a reply"><span className="sr">Waiting for a reply</span></i>}
                  </span>
                </button>
              </li>
            );
          })}
          {!shown.length && <li className="empty">No conversations match.</li>}
        </ul>
      </aside>
      <Thread key={cur.s.id} item={cur} data={data} onBack={() => setOpened(false)} />
      <Status s={cur.s} data={data} onOpen={() => pick(cur.s.id)} />
      {drawer}
    </div>
  );
}

function Thread({ item: { s, msgs, waiting }, data, onBack }: { item: Item; data: LiveData; onBack: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [msgs.length]);
  const loading = data.live && !data.events.some((e) => e.session_id === s.id);
  const who = (m: ThreadMsg) => (m.ours ? "Leylü" : m.mail.from.split("@")[0] || s.customer);
  return (
    <section className="m-thread" aria-labelledby={`th-${s.id}`}>
      <header>
        <button type="button" className="btn back" onClick={onBack}>← Conversations</button>
        <div>
          <h2 id={`th-${s.id}`}>{s.customer}</h2>
          <small className="mono">{s.booking!.booking_reference ?? s.booking!.rate_id}{msgs[0]?.mail.subject ? ` · ${msgs[0].mail.subject}` : ""}</small>
        </div>
      </header>
      <div ref={box} className="m-body" role="log" aria-label={`Mails with ${s.customer}`}>
        {msgs.map((m, i) => (
          <div key={i} className="m-item">
            {(i === 0 || dayKey(msgs[i - 1].at) !== dayKey(m.at)) && <p className="m-day"><span>{day(m.at)}</span></p>}
            <div className={`bubble${m.ours ? " ours" : ""}`}>
              <small>{who(m)} · {clockShort(m.at)}</small>
              {m.mail.body.trim()}
            </div>
          </div>
        ))}
        {!msgs.length && <p className="hint m-none">{loading ? "Loading the mails…" : "No mails stored for this booking."}</p>}
        {waiting && <p className="note m-wait">The customer&apos;s last mail has no reply yet.</p>}
      </div>
      <form className="m-input" onSubmit={(e) => e.preventDefault()}>
        <label htmlFor={`in-${s.id}`} className="sr">Message to {s.customer}</label>
        <input id={`in-${s.id}`} placeholder="Write a message" disabled aria-describedby={`in-n-${s.id}`} />
        <button className="btn dark" type="submit" disabled>Send</button>
        <small id={`in-n-${s.id}`} className="hint">Answers are sent by the assistant; use Reply myself on the request to write one.</small>
      </form>
    </section>
  );
}

function Status({ s, data, onOpen }: { s: Session; data: LiveData; onOpen: () => void }) {
  const b = s.booking!;
  const { awb, flight } = awbFlight(s, data.events);
  const bd = bookingBadge(s);
  return (
    <aside className="m-status" aria-label="Shipment">
      <h2 className="mp-h">Shipment</h2>
      {s.rfq ? (
        <div className="ship-route">
          <span><b>{city(s.rfq.origin)}</b><small className="mono">{s.rfq.origin}</small></span>
          <span className="arrow" aria-label="to">→</span>
          <span><b>{city(s.rfq.destination)}</b><small className="mono">{s.rfq.destination}</small></span>
        </div>
      ) : <p className="hint">Route not read</p>}
      <span className={`badge ${bd.tone}`}>{bd.label}</span>
      <dl className="kv">
        <div><dt>Airline</dt><dd>{b.airline ?? shortCarrier(s.quote?.carrier)}</dd></div>
        {awb && <div><dt>AWB</dt><dd className="mono">{awb}</dd></div>}
        {flight && <div><dt>Flight</dt><dd className="mono">{flight}</dd></div>}
      </dl>
      <ol className="stepper" aria-label="Shipment progress">
        {legs(s).map((l) => (
          <li key={l.label} className={l.done ? "ok" : undefined}>
            <b>{l.label}</b>
            <small className="mono">{l.done ? (l.at ? `${day(l.at)}, ${clockShort(l.at)}` : "done, time not known") : "not yet"}</small>
          </li>
        ))}
      </ol>
      <button className="btn" type="button" aria-haspopup="dialog" onClick={onOpen}>Open request</button>
    </aside>
  );
}
