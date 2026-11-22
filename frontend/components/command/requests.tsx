"use client";
// Requests (home): three stacked sections (being priced now, needs you, all requests); a request's detail opens in
// a drawer. Deep link: /command?s=<session id> opens that request's drawer.
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { BackendError, intervene } from "@/lib/api";
import { clock, matches, money, shortCarrier, transit } from "@/lib/format";
import type { LiveData } from "@/lib/live";
import { RESPONSE_FULL_S } from "@/lib/metrics";
import type { Session } from "@/lib/types";
import {
  badge, cargo, elapsed, fmt, gateNotes, group, GROUP_ORDER, initials, isChosen, priced, pricingNow, progress, reason, route,
  sourceOf, steps, thread, timing, type Group,
} from "@/lib/command/derive";
import { useCommand, useNow } from "./shell";

type Filter = "all" | Group;
const SEG: [Filter, string][] = [["all", "All"], ["need", "Needs you"], ["busy", "Pricing"], ["done", "Answered"]];

const offWhy = "Sample data: actions are off until the backend is reachable.";
// No endpoint this page may call: POST /api/sessions/{id}/portal-rate needs the X-Paste-Secret header.
const rateWhy =
  "Entering a portal price needs the paste secret (POST /api/sessions/{id}/portal-rate with X-Paste-Secret), which this page does not have. Use agent/portal_rate.py, or Reply myself with the all-in price.";
const rateShort = "Not wired up here (needs the portal paste secret). Use Reply myself with the all-in price.";

export function Requests() {
  const data = useCommand();
  const now = useNow();
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const loadEvents = data?.loadEvents;

  const id = Number(params.get("s"));
  const open = data?.sessions.find((s) => s.id === id) ?? null;
  const busy = data ? pricingNow(data.sessions) : null;
  const needs = (data?.sessions ?? []).filter((s) => group(s) === "need").sort((a, b) => Date.parse(b.received_at) - Date.parse(a.received_at));
  const needIds = needs.map((s) => s.id).join(",");

  // Live mode loads event history per session: the open one, the one being priced (steps), the needs-you ones (reason).
  useEffect(() => {
    if (!loadEvents) return;
    [open?.id, busy?.id, ...needIds.split(",").map(Number)].forEach((x) => x && loadEvents(x));
  }, [open?.id, busy?.id, needIds, loadEvents]);

  if (!data) return <p className="hint">Loading…</p>;
  const rows = data.sessions
    .filter((s) => (filter === "all" || group(s) === filter) && (!q || matches(s, q)))
    .sort((a, b) => GROUP_ORDER[group(a)] - GROUP_ORDER[group(b)] || Date.parse(b.received_at) - Date.parse(a.received_at));
  const count = (f: Filter) => data.sessions.filter((s) => f === "all" || group(s) === f).length;
  const show = (sid: number) => router.replace(`${path}?s=${sid}`, { scroll: false });
  const close = () => router.replace(path, { scroll: false });

  return (
    <div className="home">
      {busy && (
        <section className="sec" aria-labelledby="h-now">
          <div className="sec-h"><h2 id="h-now">Being priced now</h2><span>The assistant is working on this one</span></div>
          <Now s={busy} data={data} now={now} />
        </section>
      )}

      <section className="sec" aria-labelledby="h-need">
        <div className="sec-h"><h2 id="h-need">Needs you</h2><span>{needs.length ? "Only these wait for a person" : "Nothing right now"}</span></div>
        {needs.length ? (
          <div className="needs">
            {needs.map((s) => (
              <article key={s.id} className="card ncard" aria-label={s.customer}>
                <div className="t"><b>{s.customer}</b><span className="mono">{route(s)}</span></div>
                <p>{reason(s, data.events)}</p>
                <PriceBox s={s} onDetails={() => show(s.id)} />
              </article>
            ))}
          </div>
        ) : (
          <div className="card calm">All requests are being handled by the assistant.</div>
        )}
      </section>

      <section className="sec" aria-labelledby="h-all">
        <div className="sec-h"><h2 id="h-all">All requests</h2><span>Click one to see the mail and our reply</span></div>
        <div className="card">
          <div className="tb-head">
            <div className="seg" role="group" aria-label="Show">
              {SEG.map(([f, label]) => (
                <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}>
                  {label}<b>{count(f)}</b>
                </button>
              ))}
            </div>
            <label className="search">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></svg>
              <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" aria-label="Search customer, route or BK reference" />
            </label>
          </div>
          <div className="scroll">
            <table className="reqs">
              <caption className="sr">Requests: needs you first, then pricing, then answered. Press Enter on a row to open it.</caption>
              <thead>
                <tr><th scope="col">Customer</th><th scope="col">Route</th><th scope="col">Status</th><th scope="col">Answered</th><th scope="col" className="r">All-in</th></tr>
              </thead>
              <tbody>
                {rows.map((s) => {
                  const b = badge(s);
                  const t = timing(s, now);
                  return (
                    <tr
                      key={s.id}
                      className="pick"
                      tabIndex={0}
                      aria-haspopup="dialog"
                      aria-selected={s.id === open?.id}
                      onClick={() => show(s.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          show(s.id);
                        }
                      }}
                    >
                      <td>
                        <div className="whoc">
                          <span className="av" aria-hidden="true">{initials(s.customer)}</span>
                          <div><b>{s.customer}</b><small>{cargo(s)}</small></div>
                        </div>
                      </td>
                      <td className="mono">{route(s) || "—"}</td>
                      <td><span className={`badge ${b.tone}`}>{b.label}</span></td>
                      <td className={`mono${t.late ? " late" : ""}`}>{t.text}{t.late ? " late" : ""}</td>
                      <td className="mono r">{s.quote ? money(s.quote.total, s.quote.currency) : "—"}</td>
                    </tr>
                  );
                })}
                {!rows.length && <tr className="empty"><td colSpan={5}>No requests match.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {open && <Drawer s={open} data={data} now={now} onClose={close} />}
    </div>
  );
}

function Now({ s, data, now }: { s: Session; data: LiveData; now: number }) {
  const sec = elapsed(s, now);
  const late = sec > RESPONSE_FULL_S;
  const meta = s.rfq ? [cargo(s), `${s.rfq.ask} option`, s.rfq.commodity, s.rfq.dangerous_goods ? "dangerous goods" : null].filter(Boolean).join(" · ") : "Reading the mail";
  return (
    <div className="card now">
      <div className="now-top">
        <div>
          <span className="tag"><i aria-hidden="true" />{s.customer}</span>
          <div className="now-route">{s.rfq ? <>{s.rfq.origin} <span aria-label="to">→</span> {s.rfq.destination}</> : "New request"}</div>
          <div className="now-meta">{meta}</div>
        </div>
        <div className="clock">
          <b aria-label={`${fmt(sec)} since the mail arrived`}>{fmt(sec)}</b>
          <small className={late ? "late" : undefined}>{late ? "over the 2:00 target" : "on track for the 2:00 target"}</small>
        </div>
      </div>
      <ol className="big-steps" aria-label="Progress">
        {steps(s, data.events).map((x) => (
          <li
            key={x.label}
            className={`bstep${x.state === "todo" ? "" : ` ${x.state}`}`}
            aria-current={x.state === "cur" ? "step" : undefined}
            style={x.state === "cur" ? ({ "--p": `${Math.max(10, progress(s, data.events).pct)}%` } as CSSProperties) : undefined}
          >
            <b>{x.label}</b>
            <small>{x.note}</small>
          </li>
        ))}
      </ol>
    </div>
  );
}

// The needs-you price box. There is no endpoint this page may call for it, so it is shown disabled with the reason.
function PriceBox({ s, onDetails }: { s: Session; onDetails?: () => void }) {
  const inputId = `rate-${s.id}${onDetails ? "" : "-d"}`;
  return (
    <>
      <div className="f">
        <label htmlFor={inputId} className="sr">Price in EUR, all-in</label>
        <input id={inputId} placeholder="EUR, all-in" inputMode="decimal" disabled title={rateWhy} />
        <span title={rateWhy}><button className="btn red" type="button" disabled>Send the quote</button></span>
        {onDetails && <button className="btn" type="button" aria-haspopup="dialog" onClick={onDetails}>Details</button>}
      </div>
      <small className="hint">{rateShort}</small>
    </>
  );
}

export function Drawer({ s, data, now, onClose }: { s: Session; data: LiveData; now: number; onClose: () => void }) {
  const panel = useRef<HTMLElement>(null);
  const closeBtn = useRef<HTMLButtonElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  // Focus the close button on open and give focus back on close; Escape closes; Tab stays inside the dialog.
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
      if (e.key !== "Tab" || !panel.current) return;
      const f = [...panel.current.querySelectorAll<HTMLElement>("button:not(:disabled), textarea, input:not(:disabled), summary, a[href]")];
      if (!f.length) return;
      const first = f[0];
      const last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      before?.focus?.();
    };
  }, [s.id]);

  const b = badge(s);
  const t = timing(s, now);
  const g = group(s);
  const msgs = thread(data.events, s.id);
  const lastIn = msgs.filter((m) => !m.ours).at(-1);
  const lastOut = msgs.filter((m) => m.ours).at(-1);
  const p = priced(s, data.events);
  const gates = gateNotes(data.events, s.id);
  const loading = data.live && !data.events.some((e) => e.session_id === s.id);
  const airline = s.booking?.airline ?? (s.quote ? shortCarrier(s.quote.carrier) : g === "busy" ? progress(s, data.events).text : "—");
  const fallback = g === "busy" ? "The reply goes out on its own as soon as the prices are in." : g === "need" ? reason(s, data.events) : "No reply in this thread.";

  return (
    <>
      <div className="drawer-bg" onClick={onClose} aria-hidden="true" />
      <aside ref={panel} className="drawer" role="dialog" aria-modal="true" aria-labelledby={`dr-${s.id}`}>
        <button ref={closeBtn} className="x" type="button" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="m3 3 8 8M11 3l-8 8" /></svg>
        </button>
        <div>
          <div className="ln mono">{route(s) || "Route not read yet"} · #{s.id}</div>
          <h3 id={`dr-${s.id}`}>{s.customer}</h3>
        </div>
        {g === "need" && (
          <div className="need">
            <p><b>Needs you:</b> {reason(s, data.events)}</p>
            <PriceBox s={s} />
          </div>
        )}
      <dl className="kv">
        <div><dt>Status</dt><dd><span className={`badge ${b.tone}`}>{b.label}</span></dd></div>
        <div><dt>Answered in</dt><dd className={`mono${t.late ? " late" : ""}`}>{t.text}</dd></div>
        <div><dt>Airline</dt><dd>{airline}</dd></div>
        <div><dt>Customer asked</dt><dd>{s.rfq ? (s.rfq.ask === "fastest" ? "Fastest" : "Cheapest") : "—"}</dd></div>
      </dl>
      <div className="amount">
        <span>All-in price</span>
        <b>{s.quote ? money(s.quote.total, s.quote.currency) : "—"}</b>
      </div>
      <div className="thread">
        <div className="msg">
          <small>Customer{lastIn ? ` · ${clock(lastIn.at)}` : ""}</small>
          {lastIn ? lastIn.mail.body.trim() : loading ? "Loading the mail…" : "No mail text stored for this request."}
        </div>
        <div className="msg ours">
          <small>Leylü{lastOut ? ` · ${clock(lastOut.at)}` : ""}</small>
          {lastOut ? lastOut.mail.body.trim() : loading ? "Loading…" : fallback}
        </div>
      </div>
      {gates.map((n, i) => <p key={i} className="note">{n.text}</p>)}
      {(p.options.length > 0 || msgs.length > 2 || s.booking) && (
        <details>
          <summary>
            {[p.options.length && `${p.options.length} prices compared`, s.booking && "booking", msgs.length > 2 && `whole thread (${msgs.length} mails)`].filter(Boolean).join(" · ")}
          </summary>
          <div className="more">
            {p.options.map((o, i) => (
              <div key={i} className={`opt${isChosen(o, p.chosen) ? " chosen" : ""}`}>
                <span>{o.carrier} <small>· {sourceOf(o, p.remembered)} · {transit(o.transit_days)}{isChosen(o, p.chosen) ? " · chosen" : ""}</small></span>
                <span className="mono">{money(o.total, o.currency)}</span>
              </div>
            ))}
            {s.booking && (
              <div className="opt">
                <span>{s.booking.booking_reference ?? s.booking.rate_id} <small>· {s.booking.airline ?? "airline"} · {s.booking.status ?? "waiting for the airline"}</small></span>
                <span className="mono">{s.booking.confirmation ?? ""}</span>
              </div>
            )}
            {msgs.length > 2 && msgs.map((m, i) => (
              <div key={i} className={`msg${m.ours ? " ours" : ""}`}>
                <small>{m.ours ? "Leylü" : "Customer"} · {clock(m.at)} · {m.mail.subject}</small>
                {m.mail.body.trim()}
              </div>
            ))}
          </div>
        </details>
      )}
      <Actions key={s.id} s={s} data={data} />
      </aside>
    </>
  );
}

type Pending = "pause" | "resume" | "send" | null;

// Same calls as the live UI's InterveneBar: POST /api/sessions/{id}/intervene, each behind a confirmation step.
function Actions({ s, data }: { s: Session; data: LiveData }) {
  const [pending, setPending] = useState<Pending>(null);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const off = !data.live;
  const to = thread(data.events, s.id).find((m) => !m.ours)?.mail.from || s.customer;

  const run = async () => {
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      // A hand reply must not race the assistant (only the first quote in a thread counts): hold first.
      if (pending === "send" && !s.paused) data.applySession(await intervene(s.id, "pause"));
      data.applySession(await intervene(s.id, pending, pending === "send" ? body : undefined));
      setPending(null);
      setBody("");
    } catch (e) {
      setError(
        e instanceof BackendError
          ? `The backend refused it (${e.status}${e.detail ? `: ${e.detail}` : ""}). Nothing was sent.`
          : "Could not reach the backend. Nothing was sent.",
      );
    } finally {
      setBusy(false);
    }
  };

  const question =
    pending === "pause" ? `Hold this request? Nothing is sent to ${s.customer} until you release it.`
    : pending === "resume" ? "Release this request? The assistant continues on its own."
    : pending === "send" ? `Send this reply to ${to}? It cannot be unsent${s.paused ? "" : "; the request is held first"}.`
    : null;

  return (
    <>
      <div className="acts">
        <span title={off ? offWhy : undefined}>
          <button className="btn" type="button" disabled={off || busy} onClick={() => setPending(s.paused ? "resume" : "pause")}>
            {s.paused ? "Release" : "Hold"}
          </button>
        </span>
        <span title={off ? offWhy : undefined}>
          <button className="btn" type="button" disabled={off || busy} onClick={() => setPending("send")}>Reply myself</button>
        </span>
        {s.paused && <span className="badge b-warn">Held</span>}
      </div>
      {off && <p className="hint">{offWhy}</p>}
      {pending && (
        <div className="confirm" role="group" aria-label="Confirm">
          {pending === "send" && (
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              aria-label={`Reply to ${to}`}
              placeholder={s.quote ? "Write the reply as it should reach the customer." : "No quote has gone out yet, so this reply counts as the quote: state one all-in total with its currency."}
              autoFocus
            />
          )}
          <p>{question}</p>
          <div className="acts">
            <button className={`btn ${pending === "pause" ? "red" : "dark"}`} type="button" disabled={busy || (pending === "send" && !body.trim())} onClick={run}>
              {busy ? "Working…" : pending === "send" ? "Send reply" : pending === "pause" ? "Hold it" : "Release"}
            </button>
            <button className="btn" type="button" disabled={busy} onClick={() => setPending(null)}>Cancel</button>
          </div>
        </div>
      )}
      {error && <p role="alert" className="err">{error}</p>}
    </>
  );
}
