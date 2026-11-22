"use client";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import { clock, duration, money, shortCarrier } from "@/lib/format";
import { RESPONSE_FULL_S, RESPONSE_ZERO_S } from "@/lib/metrics";
import type { Event, Session } from "@/lib/types";
import { OutcomeChip } from "./chips";
import { cents, paceOf, paceText, roundSeconds, steps } from "@/lib/v2/view";

const paceBar = { ok: "bg-(--v2-done)", late: "bg-(--v2-late)", zero: "bg-(--v2-zero)" };
const paceInk = { ok: "text-(--v2-done)", late: "text-(--v2-late-text)", zero: "text-(--v2-signal-text)" };

// The live round: one RFQ from mail to booking, the 2:00 target and 6:00 limit, the one amount and its LLM cost.
export function Round({ session: s, events }: { session: Session; events: Event[] }) {
  const [now, setNow] = useState(() => Date.now());
  const running = !s.quote;
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);

  const sec = roundSeconds(s, now);
  const pace = paceOf(sec);
  const track = steps(s, events);
  const pct = (v: number) => `${Math.min(100, (v / RESPONSE_ZERO_S) * 100)}%`;
  const label = `${s.quote ? "Quoted after" : "Running for"} ${duration(Math.min(sec, 5999))}, ${paceText[pace]}`;

  return (
    <section aria-label={`Round for session #${s.id}`} className="bg-(--v2-surface) border-(--v2-rule) rounded-md border px-5 py-3">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 className="font-condensed text-2xl font-bold">
          #{s.id} {s.customer}
        </h2>
        {s.rfq && (
          <span className="text-(--v2-ink-2) text-lg">
            {s.rfq.origin} → {s.rfq.destination} · {s.rfq.ask}
          </span>
        )}
        <OutcomeChip outcome={s.outcome} />
        {s.needs_human && (
          <span className="bg-(--v2-signal) rounded-sm px-2 py-0.5 text-sm font-semibold text-white">Needs a person</span>
        )}
        <div className="ml-auto flex items-baseline gap-5">
          <Figure label="All-in" value={s.quote ? money(s.quote.total, s.quote.currency) : "–"} big />
          <Figure label="Carrier" value={s.quote ? shortCarrier(s.quote.carrier) : "–"} />
          <Figure label="LLM cost" value={cents(s.llm_cost_usd)} />
        </div>
      </div>

      <ol className="mt-3 grid grid-cols-6 gap-1.5" aria-label="Progress">
        {track.map((st) => (
          <li key={st.key} className="min-w-0">
            <div className={cn("h-2 rounded-full", st.done ? "bg-(--v2-done)" : "bg-(--v2-rule)")} />
            <p className={cn("mt-1.5 text-sm font-semibold", !st.done && "text-(--v2-ink-2) font-normal")}>
              {st.done ? "✓ " : ""}
              {st.label}
              <span className="sr-only">{st.done ? " done" : " not yet"}</span>
            </p>
            <p className="text-(--v2-ink-2) font-mono text-xs">{st.at && st.done ? clock(st.at) : " "}</p>
          </li>
        ))}
      </ol>

      <div className="mt-3 flex items-center gap-4">
        <div className="relative h-3 flex-1 rounded-full bg-(--v2-surface-2) ring-1 ring-(--v2-rule)" role="img" aria-label={label}>
          <div className={cn("absolute inset-y-0 left-0 rounded-full", paceBar[pace])} style={{ width: pct(sec) }} />
          <div className="absolute -inset-y-1 w-0.5 bg-(--v2-ink)" style={{ left: pct(RESPONSE_FULL_S) }} aria-hidden />
          <span className="text-(--v2-ink-2) absolute top-4 -translate-x-1/2 text-xs" style={{ left: pct(RESPONSE_FULL_S) }} aria-hidden>
            2:00 target
          </span>
          <span className="text-(--v2-ink-2) absolute top-4 right-0 text-xs" aria-hidden>
            6:00 limit
          </span>
        </div>
        <p className={cn("font-condensed w-80 text-right text-3xl whitespace-nowrap font-bold tabular-nums", paceInk[pace])} aria-hidden>
          {sec >= RESPONSE_ZERO_S ? "6:00+" : duration(sec)}
          <span className="ml-2 align-middle text-sm font-semibold">{s.quote ? "" : "running · "}{paceText[pace]}</span>
        </p>
      </div>
      <p className="sr-only" aria-live="polite">{s.quote ? label : ""}</p>
    </section>
  );
}

function Figure({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <div className="text-right">
      <p className="text-(--v2-ink-2) text-xs font-semibold tracking-wide uppercase">{label}</p>
      <p className={cn("font-condensed font-bold tabular-nums", big ? "text-3xl" : "text-xl")}>{value}</p>
    </div>
  );
}
