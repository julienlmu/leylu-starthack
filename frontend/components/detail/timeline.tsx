import { cn } from "@/lib/utils";
import { Empty } from "./parts";
import { clock, kindLabel, magnitude, offset, usd } from "@/lib/format";
import type { Event } from "@/lib/types";

// Every agent step in order, with what it cost. Mark size follows a fixed ramp:
// mail the customer sees > decisions > internal steps; alerts are ringed in signal red.
export function Timeline({ events, startedAt }: { events: Event[]; startedAt: string }) {
  if (!events.length) {
    return <Empty title="No steps yet">Routing, extraction, pricing and every carrier bid appear here as the agent works.</Empty>;
  }
  const total = events.reduce((sum, e) => sum + e.llm_cost_usd, 0);
  return (
    <div className="flex flex-col">
      <ol className="relative flex flex-col">
        {events.map((e, i) => {
          const mag = magnitude[e.kind];
          const last = i === events.length - 1;
          return (
            <li key={`${e.at}-${i}`} className="grid grid-cols-[4.25rem_1.5rem_minmax(0,1fr)_auto] gap-x-2">
              <div className="flex flex-col items-end pt-[1px] text-right">
                <span className="text-ink text-[0.8125rem] font-medium tabular-nums">{clock(e.at)}</span>
                <span className="text-ink-3 text-xs tabular-nums">{offset(startedAt, e.at)}</span>
              </div>
              <div className="relative flex justify-center" aria-hidden>
                {!last && <span className="bg-rule-strong absolute top-3 bottom-0 w-px" />}
                {i > 0 && <span className="bg-rule-strong absolute top-0 h-2 w-px" />}
                <span
                  className={cn(
                    "relative mt-[5px] rounded-full",
                    mag === "mail" && "bg-ink size-3",
                    mag === "decision" && "bg-[var(--st-new)] size-2.5",
                    mag === "step" && "border-ink-3 bg-paper size-2 border-[1.5px] mt-[6px]",
                    mag === "alert" && "bg-signal ring-signal/30 size-3 ring-4",
                  )}
                />
              </div>
              <div className={cn("min-w-0", last ? "pb-1" : "pb-4")}>
                <p className={cn("caption", mag === "alert" && "text-signal-text", mag === "mail" && "text-ink")}>{kindLabel[e.kind]}</p>
                <p className={cn("text-ink mt-1 text-sm leading-snug", mag === "alert" && "text-signal-text font-semibold")}>{e.text}</p>
              </div>
              <div className="pt-[1px] text-right">
                {e.llm_cost_usd > 0 ? (
                  <span className="text-ink text-[0.8125rem] font-semibold tabular-nums">{usd(e.llm_cost_usd)}</span>
                ) : (
                  <span className="text-ink-3 text-[0.8125rem] tabular-nums" title="No LLM call">
                    $0
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <p className="border-rule text-ink-2 mt-3 flex justify-between border-t pt-2.5 text-sm">
        <span>
          {events.length} steps · {events.filter((e) => e.llm_cost_usd > 0).length} LLM {events.filter((e) => e.llm_cost_usd > 0).length === 1 ? "call" : "calls"}
        </span>
        <span>
          Total <span className="text-ink font-semibold tabular-nums">{usd(total)}</span>
        </span>
      </p>
    </div>
  );
}
