"use client";
import { useCommand } from "@/components/command/shell";
import { money } from "@/lib/format";
import { rates } from "@/lib/command/derive";

// Derived and read-only: counted from each request's price options (latest priced event, else its bids).
// There is no health endpoint for the sources, so this shows use, not live status.
const SOURCES: [string, string, string][] = [
  ["Portal", "Rate portal", "Live airline prices, booked by rate ID"],
  ["Sheet", "Airline price lists", "Monthly rate sheets"],
  ["Bid", "Airlines by mail", "Asked on each request, answers within the bid window"],
  ["Web form", "Portal web form", "Used when the rate API fails"],
  ["Remembered", "Remembered portal rates", "Earlier portal prices reused while the portal is down"],
];

export default function Prices() {
  const data = useCommand();
  if (!data) return <p className="hint">Loading…</p>;
  const r = rates(data.sessions, data.events);
  const priced = data.sessions.filter((s) => s.rfq).length;
  return (
    <>
      <p className="hint">Derived from the prices of {priced} requests; read-only. Nothing here changes what the assistant uses.</p>
      <div className="grid2">
        <section className="card" aria-label="Price sources">
          {SOURCES.filter(([k], i) => i < 3 || r.sources.get(k)).map(([k, name, what]) => {
            const n = r.sources.get(k) ?? 0;
            return (
              <div key={k} className="line">
                <div><b>{name}</b><small>{what}</small></div>
                <span className={`badge ${n ? "b-good" : "b-muted"}`}>{n ? `priced ${n} request${n === 1 ? "" : "s"}` : "not used yet"}</span>
              </div>
            );
          })}
        </section>
        <section className="card" aria-label="Last price per airline">
          {r.airlines.map((a) => (
            <div key={a.carrier} className="line">
              <div><b>{a.carrier}</b><small>{a.lane}{a.quoted ? ` · quoted ${a.quoted}×` : ""}</small></div>
              <span className="mono">last {money(a.last.total, a.last.currency)}</span>
            </div>
          ))}
          {!r.airlines.length && <p className="empty">No prices collected yet.</p>}
        </section>
      </div>
    </>
  );
}
