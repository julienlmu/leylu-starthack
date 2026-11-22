"use client";
// Settings: the agent's switches as they ship (defaults from agent/*.py), read-only; only Appearance works here.
import { useTheme } from "@/components/command/shell";

type Row = { env: string; label: string; what: string } & ({ on: boolean } | { value: string; options: string[] } | { value: string; unit: string });
const SECTIONS: { id: string; title: string; rows: Row[] }[] = [
  { id: "quoting", title: "Quoting", rows: [
    { env: "QUOTE_STYLE", label: "Quote mail style", what: "Wording of the quote mail.", value: "between", options: ["between", "short", "a", "b", "classic", "human"] },
    { env: "PDF_OFFER", label: "Attach the quote as a PDF", what: "Always, only when the customer asks for a PDF, or never.", value: "always", options: ["always", "asked", "off"] },
    { env: "BID_CUTOFF_SECONDS", label: "Wait for airline bids", what: "Bids arriving later than this are left out of the quote.", value: "90", unit: "s" },
    { env: "RATEDESK", label: "Ask the rate desk when the portal is down", what: "One mail to the rate desk, then price again with its answer.", on: true },
    { env: "REQUOTE", label: "Re-quote changed shipments", what: "New figures after our quote get a new quote instead of a person.", on: true },
    { env: "FOLLOW_UP", label: "Remind quiet customers once", what: "One short reminder after the quote.", on: false },
  ] },
  { id: "booking", title: "Booking", rows: [
    { env: "EMAIL_BOOKING", label: "Book with the airline by mail", what: "Waits for the airline's confirmation.", on: true },
    { env: "CONFIRM_SENDER", label: "Accept confirmations only from the airline", what: "A \"booking confirmed\" mail counts only from the airline we booked with.", on: true },
    { env: "CANCEL_AUTO", label: "Pass cancellations to the airline", what: "Without a person; the customer hears it is being cancelled.", on: true },
    { env: "TRACKING_IN_THREAD", label: "Answer tracking questions in the quote thread", what: "From the booking, like a tracking mail.", on: true },
  ] },
  { id: "customers", title: "Customers & language", rows: [
    { env: "REPLY_LANGUAGE", label: "Reply in the customer's language", what: "Tracking, questions and reminders follow the customer's language.", on: true },
    { env: "MISSING_ASK", label: "Ask for missing shipment details", what: "Origin, destination, weight or size missing: the customer is asked.", on: true },
    { env: "INSURANCE", label: "Include cargo insurance when asked", what: "The premium goes into the all-in price.", on: true },
  ] },
  { id: "safety", title: "Safety", rows: [
    { env: "GATE_MODE", label: "Check every quote before it leaves", what: "Rules only, no AI call: enforce holds a failing quote, warn only notes it.", value: "enforce", options: ["enforce", "warn", "off"] },
    { env: "LOOKALIKE", label: "Ignore look-alike senders", what: "An address imitating a known customer gets no price.", on: true },
    { env: "SENDER_GUARD", label: "Only the customer may book its quote", what: "Another sender on a shared domain cannot accept it.", on: true },
    { env: "INJECTION_GUARD", label: "Ignore instructions hidden in mails", what: "Sentences that try to instruct the assistant never reach the model.", on: true },
    { env: "SANCTIONS", label: "Refuse sanctioned destinations", what: "Shipments to sanctioned countries are declined politely, no price.", on: true },
  ] },
];
const MENU = [...SECTIONS.map((s) => [s.id, s.title]), ["appearance", "Appearance"]];

export default function Settings() {
  const { dark, toggle } = useTheme();
  return (
    <div className="settings">
      <nav className="set-nav" aria-label="Settings sections">
        {MENU.map(([id, title]) => <a key={id} href={`#set-${id}`}>{title}</a>)}
      </nav>
      <div className="set-body">
        <p className="note">These are set in the agent&apos;s .env; this page shows them. Changes take effect when the agent restarts.</p>
        {SECTIONS.map((sec) => (
          <section key={sec.id} id={`set-${sec.id}`} className="set-sec" aria-labelledby={`h-set-${sec.id}`}>
            <h2 id={`h-set-${sec.id}`}>{sec.title}</h2>
            <div className="card">
              {sec.rows.map((r) => {
                const id = `env-${r.env}`;
                return (
                  <div key={r.env} className="set-row">
                    <div>
                      <label htmlFor={id}>{r.label}</label>
                      <small id={`${id}-d`}>{r.what} <span className="mono env">{r.env}</span></small>
                    </div>
                    {"on" in r ? (
                      <span className="switch">
                        <input id={id} type="checkbox" role="switch" checked={r.on} disabled readOnly aria-describedby={`${id}-d`} />
                        <span aria-hidden="true">{r.on ? "On" : "Off"}</span>
                      </span>
                    ) : "options" in r ? (
                      <select id={id} value={r.value} disabled aria-describedby={`${id}-d`}>
                        {r.options.map((x) => <option key={x}>{x}</option>)}
                      </select>
                    ) : (
                      <span className="unit"><input id={id} value={r.value} disabled readOnly aria-describedby={`${id}-d`} /><span>{r.unit}</span></span>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        ))}
        <section id="set-appearance" className="set-sec" aria-labelledby="h-set-appearance">
          <h2 id="h-set-appearance">Appearance</h2>
          <div className="card">
            <div className="set-row">
              <div>
                <label htmlFor="theme">Dark mode</label>
                <small id="theme-d">Stored in this browser only. Works here.</small>
              </div>
              <span className="switch">
                <input id="theme" type="checkbox" role="switch" checked={dark} onChange={toggle} aria-describedby="theme-d" />
                <span aria-hidden="true">{dark ? "On" : "Off"}</span>
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
