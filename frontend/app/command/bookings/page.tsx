"use client";
// Bookings as a shipment schedule: one group per ready date, each booking a row with a bar on the group's day scale
// from the ready date to the estimated arrival (ready date + quoted transit days).
import { type CSSProperties, type KeyboardEvent } from "react";
import { useDrawer, useEvents } from "@/components/command/bits";
import { useCommand, useNow } from "@/components/command/shell";
import { money, shortCarrier, transit } from "@/lib/format";
import type { Session } from "@/lib/types";
import { bookingBadge, cancelled, DAY_MS, legs, schedule, type DayGroup, type Slot } from "@/lib/command/derive";

const dayTick = (t: number) => new Date(t).toLocaleDateString("en-GB", { weekday: "short", day: "numeric" });
const tone = (s: Session) => (cancelled(s) ? "bad" : legs(s)[1].done ? "ok" : "wait");

export default function Bookings() {
  const data = useCommand();
  const now = useNow();
  const { pick, drawer } = useDrawer(data, now);
  const list = (data?.sessions ?? []).filter((s) => s.booking);
  useEvents(data, list.map((s) => s.id));
  if (!data) return <p className="hint">Loading…</p>;
  const { groups, unscheduled } = schedule(list, now);
  const key = (id: number) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      pick(id);
    }
  };

  return (
    <div className="home sched">
      <div className="legend" aria-label="Legend">
        <span><i className="ok" aria-hidden="true" />Confirmed by the airline</span>
        <span><i className="wait" aria-hidden="true" />Waiting for the airline</span>
        <span><i className="bad" aria-hidden="true" />Cancelled</span>
        <span><i className="nowdot" aria-hidden="true" />Now</span>
        <span className="hint">Bar = ready date → estimated arrival (ready date + quoted transit days)</span>
      </div>

      {!list.length && <div className="card calm">No bookings yet. A booking appears here once a customer accepts a quote.</div>}

      {groups.map((g) => <Group key={g.key} g={g} now={now} pick={pick} keyOpen={key} />)}

      {unscheduled.length > 0 && (
        <section className="sec" aria-labelledby="h-unsched">
          <div className="sec-h"><h2 id="h-unsched">Unscheduled</h2><span>No ready date in the request</span></div>
          <div className="card day">
            <ul>
              {unscheduled.map((s) => (
                <li key={s.id} className="srow" tabIndex={0} role="button" aria-haspopup="dialog" onClick={() => pick(s.id)} onKeyDown={key(s.id)}>
                  <Who s={s} />
                  <span className="track none">No dates known</span>
                  <b className="mono amt">{s.quote ? money(s.quote.total, s.quote.currency) : "—"}</b>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
      {drawer}
    </div>
  );
}

function Who({ s }: { s: Session }) {
  const b = s.booking!;
  const bd = bookingBadge(s);
  return (
    <span className="s-who">
      <span className="mono ref">{b.booking_reference ?? b.rate_id}</span>
      <b>{s.customer}</b>
      <small>{b.airline ?? shortCarrier(s.quote?.carrier)} · <span className={`st-${tone(s)}`}>{bd.label}</span></small>
    </span>
  );
}

function Group({ g, now, pick, keyOpen }: { g: DayGroup; now: number; pick: (id: number) => void; keyOpen: (id: number) => (e: KeyboardEvent) => void }) {
  const span = g.to - g.from;
  const x = (t: number) => `${((t - g.from) / span) * 100}%`;
  const days = Array.from({ length: Math.round(span / DAY_MS) }, (_, i) => g.from + i * DAY_MS);
  const nowIn = now >= g.from && now <= g.to;
  const id = `h-day-${g.key}`;
  return (
    <section className="sec" aria-labelledby={id}>
      <div className="sec-h"><h2 id={id}>{g.label}</h2><span>{g.rows.length} booking{g.rows.length === 1 ? "" : "s"} ready{g.key === "earlier" ? " before today" : ""}</span></div>
      <div className="card day">
        <div className="srow scale" aria-hidden="true">
          <span />
          <span className="track">
            {days.map((d) => <span key={d} className="tick" style={{ left: x(d), width: `${(DAY_MS / span) * 100}%` }}>{dayTick(d)}</span>)}
          </span>
          <span />
        </div>
        <ul>
          {g.rows.map((r: Slot) => {
            const s = r.s;
            const label = `${s.customer}: ready ${new Date(r.start).toLocaleDateString("en-GB")}${r.end ? `, arrives about ${new Date(r.end).toLocaleDateString("en-GB")}` : ", arrival not known"}`;
            return (
              <li key={s.id} className="srow" tabIndex={0} role="button" aria-haspopup="dialog" aria-label={label} onClick={() => pick(s.id)} onKeyDown={keyOpen(s.id)}>
                <Who s={s} />
                <span className="track">
                  {days.map((d) => <span key={d} className="grid" style={{ left: x(d) }} />)}
                  {r.end !== null ? (
                    <span className={`bar ${tone(s)}`} style={{ left: x(r.start), width: `${((r.end - r.start) / span) * 100}%` } as CSSProperties}>
                      <span className="mono">{s.rfq?.origin}</span>
                      <span className="mono">{s.rfq?.destination}</span>
                    </span>
                  ) : (
                    <span className={`pin ${tone(s)}`} style={{ left: x(r.start) }}><span className="mono">{s.rfq?.origin} · arrival not known</span></span>
                  )}
                  {nowIn && <span className="now-l" style={{ left: x(now) }} />}
                </span>
                <span className="s-end">
                  <b className="mono amt">{s.quote ? money(s.quote.total, s.quote.currency) : "—"}</b>
                  <small>{transit(s.quote?.transit_days)}</small>
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
