"use client";
// Prices & airlines as a comparison tool: pick a lane, see each airline's all-in from the newest request priced on it.
// Everything here is derived from the requests' price options and the event log; read-only.
import { useState } from "react";
import { useEvents } from "@/components/command/bits";
import { useCommand, useNow } from "@/components/command/shell";
import { money, shortCarrier, transit } from "@/lib/format";
import { ago, airlines, isChosen, priced, pricedAt, route, SOURCE_NAME, sourceOf, sourceStates } from "@/lib/command/derive";
import { city } from "@/lib/command/cities";

const STATUS_TONE = { Down: "b-bad", Limited: "b-warn", Working: "b-good", Idle: "b-muted" } as const;

export default function Prices() {
  const data = useCommand();
  const now = useNow();
  const withRfq = (data?.sessions ?? []).filter((s) => s.rfq);
  useEvents(data, withRfq.map((s) => s.id));
  // Newest priced request per lane, newest lane first.
  const lanes = data
    ? withRfq
        .filter((s) => priced(s, data.events).options.length)
        .sort((a, b) => pricedAt(b, data.events) - pricedAt(a, data.events))
        .filter((s, i, all) => all.findIndex((x) => route(x) === route(s)) === i)
    : [];
  const [o, setO] = useState("");
  const [d, setD] = useState("");
  const [kg, setKg] = useState("");
  if (!data) return <p className="hint">Loading…</p>;

  const origin = o || lanes[0]?.rfq!.origin || "";
  const dest = d || lanes[0]?.rfq!.destination || "";
  const origins = [...new Set(withRfq.map((s) => s.rfq!.origin))].sort();
  const dests = [...new Set(withRfq.map((s) => s.rfq!.destination))].sort();
  const hit = lanes.find((s) => s.rfq!.origin === origin && s.rfq!.destination === dest) ?? null;
  const p = hit ? priced(hit, data.events) : null;
  const cw = p?.options[0]?.chargeable_weight_kg ?? null;
  const want = Number(kg.replace(",", "."));
  // A different weight than the request's: compare per kg, never invent a total for a weight nobody priced.
  const perKg = !!cw && want > 0 && Math.abs(want - cw) > 0.5;
  const val = (x: { total: number; chargeable_weight_kg: number }) => (perKg ? x.total / x.chargeable_weight_kg : x.total);
  const bars = p ? [...p.options].sort((a, b) => val(a) - val(b)) : [];
  const max = Math.max(...bars.map(val), 1);
  const states = sourceStates(data.sessions, data.events, now);
  const table = airlines(data.sessions, data.events);

  return (
    <div className="home prices">
      <p className="hint">Derived from the price options of {withRfq.length} requests and the event log. Read-only: nothing here changes what the assistant uses.</p>

      <section className="card check" aria-labelledby="h-check">
        <h2 id="h-check">Check a route</h2>
        <form className="check-f" onSubmit={(e) => e.preventDefault()}>
          <label>
            <span>From</span>
            <select value={origin} onChange={(e) => setO(e.target.value)}>
              {origins.map((x) => <option key={x} value={x}>{x} · {city(x)}</option>)}
            </select>
          </label>
          <label>
            <span>To</span>
            <select value={dest} onChange={(e) => setD(e.target.value)}>
              {dests.map((x) => <option key={x} value={x}>{x} · {city(x)}</option>)}
            </select>
          </label>
          <label>
            <span>Chargeable kg</span>
            <input inputMode="decimal" value={kg} onChange={(e) => setKg(e.target.value)} placeholder={cw ? String(cw) : "kg"} />
          </label>
        </form>
        {lanes.length > 0 && (
          <div className="lanes" role="group" aria-label="Lanes with prices">
            <span className="hint">Lanes with prices:</span>
            {lanes.map((s) => (
              <button key={s.id} type="button" className="chip mono" aria-pressed={s.id === hit?.id} onClick={() => { setO(s.rfq!.origin); setD(s.rfq!.destination); }}>
                {route(s)}
              </button>
            ))}
          </div>
        )}

        <div className="result" aria-live="polite">
          {hit && p ? (
            <>
              <p className="res-h">
                <b>{city(origin)} → {city(dest)}</b>
                <span className="hint">
                  {perKg ? "All-in per kg" : "All-in"} from request #{hit.id} ({hit.customer}), {cw} kg chargeable, priced {ago(new Date(pricedAt(hit, data.events)).toISOString(), now)}
                  {perKg ? `. No prices are known for ${want} kg, so airlines are compared per kg.` : ""}
                </span>
              </p>
              <ol className="bars" aria-label={`${perKg ? "Per-kg" : "All-in"} price per airline, cheapest first`}>
                {bars.map((x, i) => {
                  const v = val(x);
                  const text = perKg ? `${money(v, x.currency)}/kg` : money(v, x.currency);
                  return (
                    <li key={i} className={i === 0 ? "best" : undefined}>
                      <span className="b-name">{shortCarrier(x.carrier)}{isChosen(x, p.chosen) && <small> · quoted</small>}</span>
                      <span className="b-track"><span className="b-fill"><i style={{ width: `${Math.max(3, (v / max) * 100)}%` }} /></span><b className="mono">{text}</b></span>
                      <span className="badge b-muted src">{SOURCE_NAME[sourceOf(x, p.remembered)]}</span>
                      <span className="mono b-days">{transit(x.transit_days)}</span>
                      {i === 0 && <span className="sr">cheapest</span>}
                    </li>
                  );
                })}
              </ol>
            </>
          ) : (
            <p className="calm-in">No prices for {origin} → {dest} yet. Pick a lane with prices above.</p>
          )}
        </div>
      </section>

      <section className="sec" aria-labelledby="h-src">
        <div className="sec-h"><h2 id="h-src">Price sources</h2><span>Read from the event log of the last 30 minutes</span></div>
        <div className="src-grid">
          {states.map((x) => (
            <div key={x.name} className={`card src-c s-${x.status.toLowerCase()}`}>
              <span className="src-top"><b>{x.name}</b><span className={`badge ${STATUS_TONE[x.status]}`}>{x.status}</span></span>
              <small>{x.what}</small>
              <span className="src-n">{x.note}{x.last !== null ? ` · last used ${ago(new Date(x.last).toISOString(), now)}` : ""}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="sec" aria-labelledby="h-air">
        <div className="sec-h"><h2 id="h-air">Airlines</h2><span>Newest price per airline across all requests</span></div>
        <div className="card scroll">
          <table>
            <caption className="sr">Airlines, newest price first</caption>
            <thead><tr><th scope="col">Airline</th><th scope="col">Sources seen</th><th scope="col" className="r">Last price</th><th scope="col">On</th><th scope="col">Last seen</th></tr></thead>
            <tbody>
              {table.map((a) => (
                <tr key={a.carrier}>
                  <td><b>{a.carrier}</b></td>
                  <td>{[...a.sources].join(", ")}</td>
                  <td className="mono r">{money(a.last.total, a.last.currency)}</td>
                  <td className="mono">{route(a.s)} · {a.last.chargeable_weight_kg} kg</td>
                  <td className="hint">{ago(new Date(a.at).toISOString(), now)}</td>
                </tr>
              ))}
              {!table.length && <tr className="empty"><td colSpan={5}>No prices collected yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
