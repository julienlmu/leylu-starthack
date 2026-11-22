// Read-only on purpose: the switches live in the agent's environment and no API changes them.
const SWITCHES: [string, string, string, string][] = [
  ["Check every quote before it leaves", "Rules only, no AI call: holds a quote that fails a check.", "GATE_MODE", "enforce"],
  ["Probe the rate portal early", "If the portal is down, a person gets the web-form inputs at once.", "PORTAL_PROBE", "on"],
  ["Use the portal's web form as fallback", "When the rate API fails, the price is read from the web form.", "PORTAL_FORM", "on"],
  ["Ignore instructions hidden in mails", "Sentences that try to instruct the assistant never reach the model.", "INJECTION_GUARD", "on"],
  ["Include cargo insurance when asked", "The premium goes into the all-in price.", "INSURANCE", "on"],
  ["Book with the airline by mail", "Waits for the airline's confirmation.", "EMAIL_BOOKING", "on"],
  ["Pass cancellations to the airline", "Without a person.", "CANCEL_AUTO", "on"],
  ["Answer tracking questions in the quote thread", "From the booking, like a tracking mail.", "TRACKING_IN_THREAD", "on"],
  ["Remind quiet customers once", "One short reminder 2:30 after the quote.", "FOLLOW_UP", "off"],
];

export default function Settings() {
  return (
    <>
      <p className="hint">Read-only. These switches are changed in the agent&apos;s .env and take effect on restart; this page cannot change them.</p>
      <section className="card" aria-label="Assistant switches">
        {SWITCHES.map(([name, what, env, def]) => (
          <div key={env} className="line">
            <div><b>{name}</b><small>{what} <span className="k">{env}</span></small></div>
            <span className={`badge ${def === "off" ? "b-muted" : "b-good"}`}>{def === "off" ? "Off" : def === "on" ? "On" : def} by default</span>
          </div>
        ))}
      </section>
    </>
  );
}
