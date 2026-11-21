import { useState } from "react";
import { duration } from "@/lib/format";
import { RESPONSE_FULL_S, RESPONSE_ZERO_S } from "@/lib/metrics";
import type { Session } from "@/lib/types";

// One series: seconds from RFQ to quote, per quote in time order. Fixed 0–6:00 scale so the
// 2:00 (full points) and 6:00 (lost) limits stay put. The quotes table is this chart's table view.
export function ResponseChart({ quoted, seconds }: { quoted: Session[]; seconds: (s: Session) => number | null }) {
  const [hover, setHover] = useState<number | null>(null);
  const ticks = [0, 120, 240, 360];
  const pct = (s: number) => `${(Math.min(s, RESPONSE_ZERO_S) / RESPONSE_ZERO_S) * 100}%`;

  if (quoted.length === 0) return <p className="text-muted-foreground text-sm">No quotes yet.</p>;

  return (
    <div className="flex gap-2">
      {/* y-axis */}
      <div className="relative h-48 w-9 shrink-0 font-mono text-[11px] text-ink-3 tabular-nums">
        {ticks.map((t) => (
          <span key={t} className="absolute right-0 translate-y-1/2" style={{ bottom: pct(t) }}>
            {duration(t)}
          </span>
        ))}
      </div>

      <div className="relative h-48 flex-1">
        {/* gridlines + limits */}
        {ticks.map((t) => (
          <div key={t} className={`absolute inset-x-0 h-px ${t === 0 ? "bg-rule-strong" : "bg-rule"}`} style={{ bottom: pct(t) }} />
        ))}
        <div className="absolute inset-x-0 h-px bg-ink" style={{ bottom: pct(RESPONSE_FULL_S) }}>
          <span className="absolute -top-4 right-0 bg-paper caption px-1">2:00 target</span>
        </div>

        {/* columns */}
        <div className="absolute inset-0 flex items-end gap-0.5">
          {quoted.map((s, i) => {
            const sec = seconds(s) ?? 0;
            return (
              <button
                key={s.id}
                type="button"
                aria-label={`#${s.id} ${s.customer}: quoted after ${duration(sec)}`}
                onPointerEnter={() => setHover(i)}
                onPointerLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                className="relative flex h-full min-w-0 flex-1 items-end justify-center outline-none"
              >
                <span
                  className={`block w-full max-w-6 rounded-t-[4px] bg-[#2a78d6] transition-opacity ${hover !== null && hover !== i ? "opacity-50" : ""}`}
                  style={{ height: pct(sec) }}
                />
                {hover === i && (
                  <span className="pointer-events-none absolute z-10 border-rule bg-paper rounded-sm border px-2 py-1 text-left whitespace-nowrap shadow-sm" style={{ bottom: `calc(${pct(sec)} + 6px)` }}>
                    <span className="block font-condensed text-ink text-lg leading-tight font-bold">{duration(sec)}</span>
                    <span className="block text-ink-2 text-xs">
                      #{s.id} {s.customer}
                      {s.rfq ? ` · ${s.rfq.origin} → ${s.rfq.destination}` : ""}
                    </span>
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
