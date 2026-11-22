"use client";
// Sent quotes as a sales pipeline: a funnel bar (sent → answered → accepted), then one column per customer answer.
import { useState, type CSSProperties } from "react";
import { Search, useDrawer } from "@/components/command/bits";
import { useCommand, useNow } from "@/components/command/shell";
import { matches, money, shortCarrier } from "@/lib/format";
import { ago, answerOf, cityRoute, funnel, sums, type Answer } from "@/lib/command/derive";

const COLS: [Answer, string, string][] = [
  ["waiting", "Waiting", "The customer has the price"],
  ["accepted", "Accepted", "Booked with the airline"],
  ["declined", "Declined", "The customer said no"],
  ["expired", "Expired", "No answer before the price ran out"],
];

export default function Quotes() {
  const data = useCommand();
  const now = useNow();
  const { pick, drawer } = useDrawer(data, now);
  const [q, setQ] = useState("");
  if (!data) return <p className="hint">Loading…</p>;

  const quoted = data.sessions.filter((s) => s.quote).sort((a, b) => Date.parse(b.quote!.sent_at) - Date.parse(a.quote!.sent_at));
  const f = funnel(quoted);
  const shown = quoted.filter((s) => !q || matches(s, q));
  const age = (iso: string) => Math.max(0, now - Date.parse(iso)) || 0;
  const oldest = Math.max(1, ...quoted.filter((s) => answerOf(s) === "waiting").map((s) => age(s.quote!.sent_at)));
  const pct = (n: number) => (f.sent ? (n / f.sent) * 100 : 0);

  return (
    <div className="home pipe">
      <section className="card funnel" aria-labelledby="h-funnel">
        <h2 id="h-funnel" className="sr">Funnel</h2>
        <p className="funnel-t">
          <span><b>Sent</b> {f.sent}</span>
          <span aria-hidden="true">→</span>
          <span><b>Answered</b> {f.answered}</span>
          <span aria-hidden="true">→</span>
          <span><b>Accepted</b> {f.accepted}</span>
          {f.sent > 0 && <small>{Math.round(pct(f.accepted))}% of sent quotes accepted</small>}
        </p>
        <div className="funnel-bar" aria-hidden="true">
          <i style={{ width: "100%" }} />
          <i className="ans" style={{ width: `${pct(f.answered)}%` }} />
          <i className="acc" style={{ width: `${pct(f.accepted)}%` }} />
        </div>
      </section>

      <div className="board-h">
        <Search value={q} onChange={setQ} label="Search customer, route or airline" />
        <span className="hint">Click a card to see the mail and our reply</span>
      </div>

      <div className="board" role="list" aria-label="Quotes by the customer's answer">
        {COLS.map(([a, label, what]) => {
          const cards = shown.filter((s) => answerOf(s) === a);
          return (
            <section key={a} className={`col col-${a}`} role="listitem" aria-labelledby={`col-${a}`}>
              <header>
                <h2 id={`col-${a}`}>{label} <span className="n">{cards.length}</span></h2>
                <span className="mono">{sums(cards) || "—"}</span>
                <small>{what}</small>
              </header>
              <ul>
                {cards.map((s) => (
                  <li key={s.id}>
                    <button type="button" className="qcard" aria-haspopup="dialog" onClick={() => pick(s.id)}>
                      <span className="qc-who">{s.customer}</span>
                      <span className="qc-route">{cityRoute(s) || "Route not read"}</span>
                      <span className="qc-air">{shortCarrier(s.quote!.carrier)}</span>
                      <b className="qc-amt">{money(s.quote!.total, s.quote!.currency)}</b>
                      <small className="qc-ago">sent {ago(s.quote!.sent_at, now)}</small>
                      {a === "waiting" && (
                        <span className="age" aria-hidden="true">
                          <i style={{ "--w": `${Math.max(4, (age(s.quote!.sent_at) / oldest) * 100)}%` } as CSSProperties} />
                        </span>
                      )}
                    </button>
                  </li>
                ))}
                {!cards.length && <li className="col-empty">{q ? "No match" : "None"}</li>}
              </ul>
            </section>
          );
        })}
      </div>
      {drawer}
    </div>
  );
}
