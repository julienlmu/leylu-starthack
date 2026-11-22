"use client";
// Bookings: at a glance, the ones still waiting for the airline, then every booking as a shipment card.
import { Stat, Tiles, useDrawer, useEvents } from "@/components/command/bits";
import { useCommand, useNow } from "@/components/command/shell";
import { clockShort, money, moneyShort, shortCarrier } from "@/lib/format";
import type { Session } from "@/lib/types";
import { city } from "@/lib/command/cities";
import { ago, awbFlight, bookingBadge, cancelled, cargo, initials, legs } from "@/lib/command/derive";

const bookedAt = (s: Session) => Date.parse(s.booking?.booked_at ?? s.received_at);

export default function Bookings() {
  const data = useCommand();
  const now = useNow();
  const { pick, drawer } = useDrawer(data, now);
  const list = (data?.sessions ?? []).filter((s) => s.booking).sort((a, b) => bookedAt(b) - bookedAt(a));
  useEvents(data, list.map((s) => s.id));
  if (!data) return <p className="hint">Loading…</p>;

  const confirmed = list.filter((s) => legs(s)[1].done).length;
  const awaiting = list.filter((s) => !legs(s)[1].done && !cancelled(s));
  // Value booked in EUR only: other currencies are not converted here, so they are left out and named.
  const eur = list.filter((s) => s.quote?.currency === "EUR" && !cancelled(s));
  const value = eur.reduce((sum, s) => sum + s.quote!.total, 0);
  const otherCcy = list.filter((s) => s.quote && s.quote.currency !== "EUR" && !cancelled(s)).length;

  return (
    <div className="home">
      <Tiles>
        <Stat label="Bookings" value={list.length} note={list.length ? `latest ${ago(list[0].booking!.booked_at ?? list[0].received_at, now)}` : "none yet"} />
        <Stat label="Value booked" value={moneyShort(value, "EUR")} note={otherCcy ? `all-in, EUR only (${otherCcy} in other currencies)` : "sum of the all-in prices"} />
        <Stat label="Confirmed by the airline" value={<>{confirmed}<small className="of"> / {list.length}</small></>} note="airline sent its confirmation" />
        <Stat label="Awaiting confirmation" value={awaiting.length} note={awaiting.length ? "no airline confirmation yet" : "nothing open"} warn={awaiting.length > 0} />
      </Tiles>

      {awaiting.length > 0 && (
        <section className="sec" aria-labelledby="h-await">
          <div className="sec-h"><h2 id="h-await">Awaiting airline confirmation</h2><span>Booked on the portal; the airline has not confirmed yet</span></div>
          <div className="needs">
            {awaiting.map((s) => (
              <button key={s.id} type="button" className="card qrow" aria-haspopup="dialog" onClick={() => pick(s.id)}>
                <span className="av" aria-hidden="true">{initials(s.customer)}</span>
                <span className="qmain">
                  <b>{s.customer}</b>
                  <span className="qroute">{s.rfq ? `${city(s.rfq.origin)} → ${city(s.rfq.destination)}` : "—"}</span>
                  <small>{[s.booking!.booking_reference ?? s.booking!.rate_id, s.booking!.airline ?? shortCarrier(s.quote?.carrier)].join(" · ")}</small>
                </span>
                <span className="qside">
                  <span className={`badge ${bookingBadge(s).tone}`}>{bookingBadge(s).label}</span>
                  <small>{s.booking!.booked_at ? `booked ${ago(s.booking!.booked_at, now)}` : ""}</small>
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="sec" aria-labelledby="h-allb">
        <div className="sec-h"><h2 id="h-allb">All bookings</h2><span>Newest first. Click one to see the mail and our reply</span></div>
        {list.length ? (
          <div className="bgrid">
            {list.map((s) => {
              const b = s.booking!;
              const bd = bookingBadge(s);
              const { awb, flight } = awbFlight(s, data.events);
              return (
                // The whole card is clickable through the stretched button (a list cannot sit inside a button).
                <article key={s.id} className="card bcard" aria-label={`${s.customer}, ${b.booking_reference ?? b.rate_id}`}>
                  <span className="bc-top">
                    <button type="button" className="stretch mono" aria-haspopup="dialog" onClick={() => pick(s.id)}>{b.booking_reference ?? b.rate_id}</button>
                    <span className={`badge ${bd.tone}`}>{bd.label}</span>
                  </span>
                  {s.rfq ? (
                    <span className="bc-route">
                      <span><b>{city(s.rfq.origin)}</b><small className="mono">{s.rfq.origin}</small></span>
                      <span className="arrow" aria-label="to">→</span>
                      <span><b>{city(s.rfq.destination)}</b><small className="mono">{s.rfq.destination}</small></span>
                    </span>
                  ) : (
                    <span className="bc-route"><b>Route not read</b></span>
                  )}
                  <span className="bc-who">
                    <span><b>{s.customer}</b><small>{b.airline ?? shortCarrier(s.quote?.carrier)}</small></span>
                    <b className="amt">{s.quote ? money(s.quote.total, s.quote.currency) : "—"}</b>
                  </span>
                  <span className="bc-facts">
                    {awb && <span><small>AWB</small><b className="mono">{awb}</b></span>}
                    {flight && <span><small>Flight</small><b className="mono">{flight}</b></span>}
                    <span><small>Cargo</small><b>{cargo(s)}</b></span>
                  </span>
                  <ol className="trip" aria-label="Shipment progress">
                    {legs(s).map((l) => (
                      <li key={l.label} className={l.done ? "ok" : undefined}>
                        <b>{l.label}</b>
                        <small>{l.done ? (l.at ? clockShort(l.at) : "done") : "not yet"}</small>
                      </li>
                    ))}
                  </ol>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="card calm">No bookings yet. A booking appears here once a customer accepts a quote.</div>
        )}
      </section>
      {drawer}
    </div>
  );
}
