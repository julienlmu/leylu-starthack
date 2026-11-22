"use client";
// Shipment tracking: at a glance, then the booked shipments (left) and the selected one in full (right):
// route, a status timeline and the latest customer question with our answer.
import { useState } from "react";
import { Search, Stat, Tiles, useDrawer, useEvents } from "@/components/command/bits";
import { useCommand, useNow } from "@/components/command/shell";
import { clockShort, matches, shortCarrier } from "@/lib/format";
import type { LiveData } from "@/lib/live";
import type { Session } from "@/lib/types";
import { city } from "@/lib/command/cities";
import { awbFlight, bookingBadge, fmt, route, trackingOf } from "@/lib/command/derive";

type Item = { s: Session; t: ReturnType<typeof trackingOf> };

export default function Tracking() {
  const data = useCommand();
  const now = useNow();
  const { pick, drawer } = useDrawer(data, now);
  const [sel, setSel] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const booked = (data?.sessions ?? []).filter((s) => s.booking);
  useEvents(data, booked.map((s) => s.id));
  if (!data) return <p className="hint">Loading…</p>;

  const items: Item[] = booked
    .map((s) => ({ s, t: trackingOf(s, data.events) }))
    .sort((a, b) => (b.t.newest ?? 0) - (a.t.newest ?? 0) || Date.parse(b.s.booking!.booked_at ?? "") - Date.parse(a.s.booking!.booked_at ?? ""));
  const answers = items.flatMap((i) => i.t.answers);
  const waiting = items.filter((i) => i.t.waiting).length;
  const asked = answers.length + waiting;
  const timed = answers.map((a) => a.sec).filter((x): x is number => x !== null);
  const avg = timed.length ? Math.round(timed.reduce((a, b) => a + b, 0) / timed.length) : null;
  const shown = items.filter((i) => !q || matches(i.s, q));
  const cur = items.find((i) => i.s.id === sel) ?? items[0];

  return (
    <div className="home">
      <Tiles>
        <Stat label="Tracking questions" value={asked} note={waiting ? `${waiting} still waiting for a reply` : "customers asking where their shipment is"} warn={waiting > 0} />
        <Stat label="Answered automatically" value={asked ? `${Math.round((answers.length / asked) * 100)}%` : "—"} note={`${answers.length} of ${asked} answered from the CRM`} />
        <Stat label="Average answer time" value={avg === null ? "—" : fmt(avg)} note={timed.length ? `over ${timed.length} question${timed.length === 1 ? "" : "s"} with the mail stored` : "no question mail stored yet"} />
      </Tiles>

      <section className="sec" aria-labelledby="h-ship">
        <div className="sec-h"><h2 id="h-ship">Booked shipments</h2><span>Newest question first</span></div>
        {items.length ? (
          <div className="md">
            <div className="card md-list">
              <div className="tb-head"><Search value={q} onChange={setQ} label="Search customer, route or BK reference" /></div>
              <ul aria-label="Shipments">
                {shown.map(({ s, t }) => {
                  const bd = bookingBadge(s);
                  return (
                    <li key={s.id}>
                      <button type="button" aria-pressed={s.id === cur.s.id} onClick={() => setSel(s.id)}>
                        <span className="ml-top"><b>{s.customer}</b>{t.waiting && <span className="dot" title="Question waiting"><span className="sr">Question waiting</span></span>}</span>
                        <span className="ml-sub mono">{s.booking!.booking_reference ?? s.booking!.rate_id} · {route(s) || "—"}</span>
                        <span className={`badge ${bd.tone}`}>{bd.label}</span>
                      </button>
                    </li>
                  );
                })}
                {!shown.length && <li className="empty">No shipments match.</li>}
              </ul>
            </div>
            <Detail item={cur} data={data} onOpen={() => pick(cur.s.id)} />
          </div>
        ) : (
          <div className="card calm">No bookings yet. Tracking questions appear here once a booked customer asks where the shipment is.</div>
        )}
      </section>
      {drawer}
    </div>
  );
}

function Detail({ item: { s, t }, data, onOpen }: { item: Item; data: LiveData; onOpen: () => void }) {
  const b = s.booking!;
  const { awb, flight } = awbFlight(s, data.events);
  const last = t.answers.at(-1);
  const loading = data.live && !data.events.some((e) => e.session_id === s.id);
  type Row = { at: string; label: string; text?: string; tone: string };
  const rows: Row[] = [
    ...(b.booked_at ? [{ at: b.booked_at, label: "Booked on the portal", text: `${b.booking_reference ?? b.rate_id} · ${b.airline ?? shortCarrier(s.quote?.carrier)}`, tone: "ok" }] : []),
    ...s.status_updates.map((u) => ({ at: u.at, label: /confirmed/i.test(u.text) && !/cancel/i.test(u.text) ? "Airline confirmed" : "Status update", text: u.text, tone: "ok" })),
    ...t.answers.flatMap((a) => [
      ...(a.q ? [{ at: a.q.at, label: "Customer asked", text: a.q.mail.subject, tone: "ask" }] : []),
      { at: a.a.at, label: `Answered from the CRM${a.sec !== null ? ` in ${fmt(a.sec)}` : ""}`, tone: "ans" },
    ]),
    ...(t.waiting ? [{ at: t.waiting.at, label: "Customer asked, no reply yet", text: t.waiting.mail?.subject, tone: "wait" }] : []),
  ].sort((x, y) => Date.parse(x.at) - Date.parse(y.at));
  const bd = bookingBadge(s);

  return (
    <article className="card md-panel" aria-labelledby={`tr-${s.id}`}>
      <div className="mp-head">
        <div>
          <div className="ln mono">{b.booking_reference ?? b.rate_id}{awb ? ` · AWB ${awb}` : ""}{flight ? ` · ${flight}` : ""}</div>
          <h3 id={`tr-${s.id}`}>{s.customer}</h3>
        </div>
        <div className="acts">
          <span className={`badge ${bd.tone}`}>{bd.label}</span>
          <button className="btn" type="button" aria-haspopup="dialog" onClick={onOpen}>Open request</button>
        </div>
      </div>
      <div className="now-route">
        {s.rfq ? <>{city(s.rfq.origin)} <span aria-label="to">→</span> {city(s.rfq.destination)}</> : "Route not read"}
      </div>
      <div className="now-meta">{[b.airline ?? shortCarrier(s.quote?.carrier), route(s)].filter(Boolean).join(" · ")}</div>
      <div className="mp-body">
        <div>
          <h4 className="mp-h">Timeline</h4>
          {rows.length ? (
            <ol className="tl">
              {rows.map((r, i) => (
                <li key={i} className={r.tone}>
                  <b>{r.label}</b>
                  <small className="mono">{clockShort(r.at)}</small>
                  {r.text && <span>{r.text}</span>}
                </li>
              ))}
            </ol>
          ) : (
            <p className="hint">{loading ? "Loading…" : "No times stored for this booking."}</p>
          )}
        </div>
        <div>
          <h4 className="mp-h">Latest question</h4>
          {t.waiting ? (
            <div className="thread">
              <div className="msg"><small>Customer · {clockShort(t.waiting.at)}</small>{t.waiting.mail?.body.trim() ?? "No mail text stored."}</div>
              <p className="note">No reply yet. Open the request to answer it yourself.</p>
            </div>
          ) : last ? (
            <div className="thread">
              {last.q && <div className="msg"><small>Customer · {clockShort(last.q.at)}</small>{last.q.mail.body.trim()}</div>}
              <div className="msg ours"><small>Leylü · {clockShort(last.a.at)}</small>{last.reply?.body.trim() ?? last.a.text}</div>
            </div>
          ) : (
            <div className="calm-in">{loading ? "Loading…" : "The customer has not asked about this shipment yet."}</div>
          )}
        </div>
      </div>
    </article>
  );
}
