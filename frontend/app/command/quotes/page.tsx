"use client";
// Sent quotes: at a glance, the quotes still waiting for the customer, then every quote with a filter.
import { useState, type KeyboardEvent } from "react";
import { Search, Stat, Tiles, useDrawer } from "@/components/command/bits";
import { useCommand, useNow } from "@/components/command/shell";
import { matches, money, responseSeconds, shortCarrier } from "@/lib/format";
import { RESPONSE_FULL_S } from "@/lib/metrics";
import type { Session } from "@/lib/types";
import { ago, ANSWER, answerOf, cargo, cityRoute, fmt, initials, quoteStats, route, type Answer } from "@/lib/command/derive";

type Filter = "all" | Answer;
const SEG: [Filter, string][] = [["all", "All"], ["waiting", "Waiting"], ["accepted", "Accepted"], ["declined", "Declined"], ["expired", "Expired"]];

export default function Quotes() {
  const data = useCommand();
  const now = useNow();
  const { pick, drawer } = useDrawer(data, now);
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  if (!data) return <p className="hint">Loading…</p>;

  const quoted = data.sessions.filter((s) => s.quote).sort((a, b) => Date.parse(b.quote!.sent_at) - Date.parse(a.quote!.sent_at));
  const st = quoteStats(quoted);
  const waiting = quoted.filter((s) => answerOf(s) === "waiting");
  const rows = quoted.filter((s) => (filter === "all" || answerOf(s) === filter) && (!q || matches(s, q)));
  const count = (f: Filter) => quoted.filter((s) => f === "all" || answerOf(s) === f).length;
  const slow = st.medianSec !== null && st.medianSec > RESPONSE_FULL_S;
  const keyOpen = (s: Session) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      pick(s.id);
    }
  };

  return (
    <div className="home">
      <Tiles>
        <Stat label="Waiting for an answer" value={st.waiting} note={`of ${quoted.length} quote${quoted.length === 1 ? "" : "s"} sent`} />
        <Stat label="Accepted" value={st.accepted} note="booked with the airline" />
        <Stat label="Win rate" value={st.winRate === null ? "—" : `${st.winRate}%`} note="accepted of all answered or expired" />
        <Stat label="Median time to quote" value={st.medianSec === null ? "—" : fmt(st.medianSec)} note={slow ? "over the 2:00 target" : "target 2:00"} warn={slow} />
      </Tiles>

      <section className="sec" aria-labelledby="h-wait">
        <div className="sec-h"><h2 id="h-wait">Waiting for an answer</h2><span>{waiting.length ? "The customer has the price; a yes books it" : "Nothing open"}</span></div>
        {waiting.length ? (
          <div className="needs">
            {waiting.map((s) => {
              const sec = responseSeconds(s);
              return (
                <button key={s.id} type="button" className="card qrow" aria-haspopup="dialog" onClick={() => pick(s.id)}>
                  <span className="av" aria-hidden="true">{initials(s.customer)}</span>
                  <span className="qmain">
                    <b>{s.customer}</b>
                    <span className="qroute">{cityRoute(s) || "—"}</span>
                    <small>{[shortCarrier(s.quote!.carrier), cargo(s), route(s)].filter(Boolean).join(" · ")}</small>
                  </span>
                  <span className="qside">
                    <b className="big">{money(s.quote!.total, s.quote!.currency)}</b>
                    <small>
                      sent {ago(s.quote!.sent_at, now)}
                      {sec !== null && <> · answered in <span className={`mono${sec > RESPONSE_FULL_S ? " late" : ""}`}>{fmt(sec)}</span></>}
                    </small>
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="card calm">{quoted.length ? "Every quote has an answer." : "No quotes sent yet."}</div>
        )}
      </section>

      <section className="sec" aria-labelledby="h-allq">
        <div className="sec-h"><h2 id="h-allq">All quotes</h2><span>Click one to see the mail and our reply</span></div>
        <div className="card">
          <div className="tb-head">
            <div className="seg" role="group" aria-label="Show">
              {SEG.map(([f, label]) => (
                <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
                  {label}<b>{count(f)}</b>
                </button>
              ))}
            </div>
            <Search value={q} onChange={setQ} label="Search customer, route or airline" />
          </div>
          <div className="scroll">
            <table className="reqs">
              <caption className="sr">Sent quotes, newest first. Press Enter on a row to open it.</caption>
              <thead>
                <tr><th scope="col">Customer</th><th scope="col">Route</th><th scope="col">Airline</th><th scope="col">Sent</th><th scope="col">Answered in</th><th scope="col">Customer&apos;s answer</th><th scope="col" className="r">All-in</th></tr>
              </thead>
              <tbody>
                {rows.map((s) => {
                  const sec = responseSeconds(s);
                  const [label, tone] = ANSWER[answerOf(s)];
                  return (
                    <tr key={s.id} className="pick" tabIndex={0} aria-haspopup="dialog" onClick={() => pick(s.id)} onKeyDown={keyOpen(s)}>
                      <td>
                        <div className="whoc">
                          <span className="av" aria-hidden="true">{initials(s.customer)}</span>
                          <div><b>{s.customer}</b><small>{cargo(s)}</small></div>
                        </div>
                      </td>
                      <td className="mono">{route(s) || "—"}</td>
                      <td>{shortCarrier(s.quote!.carrier)}</td>
                      <td className="hint">{ago(s.quote!.sent_at, now)}</td>
                      <td className={`mono${sec !== null && sec > RESPONSE_FULL_S ? " late" : ""}`}>{sec === null ? "—" : fmt(sec)}</td>
                      <td><span className={`badge ${tone}`}>{label}</span></td>
                      <td className="mono r">{money(s.quote!.total, s.quote!.currency)}</td>
                    </tr>
                  );
                })}
                {!rows.length && <tr className="empty"><td colSpan={7}>{quoted.length ? "No quotes match." : "No quotes sent yet."}</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </section>
      {drawer}
    </div>
  );
}
