import { duration, responseSeconds } from "@/lib/format";
import { metrics } from "@/lib/metrics";
import type { Session } from "@/lib/types";
import { cents } from "@/lib/v2/view";

// Four numbers a jury reads at a glance.
export function KpiStrip({ sessions }: { sessions: Session[] }) {
  const m = metrics(sessions);
  const times = sessions.map(responseSeconds).filter((v): v is number => v !== null).sort((a, b) => a - b);
  const median = times.length ? times[Math.floor(times.length / 2)] : null;
  const kpis = [
    { label: "Accepted", value: m.quoted.length ? `${Math.round((m.won / m.quoted.length) * 100)}%` : "–", note: `${m.won} of ${m.quoted.length} quotes` },
    { label: "Median response", value: median === null ? "–" : duration(median), note: "target 2:00" },
    { label: "LLM cost / RFQ", value: m.sessions ? cents(m.totalCost / m.sessions) : "–", note: `${m.sessions} RFQs` },
    { label: "Bookings", value: String(m.booked.length), note: "by rate ID" },
  ];
  return (
    <dl className="flex gap-6">
      {kpis.map((k) => (
        <div key={k.label} className="min-w-0">
          <dt className="text-(--v2-ink-2) text-xs font-semibold tracking-wide uppercase">{k.label}</dt>
          <dd className="font-condensed text-2xl leading-tight font-bold tabular-nums">
            {k.value} <span className="text-(--v2-ink-2) font-sans text-xs font-normal">{k.note}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
