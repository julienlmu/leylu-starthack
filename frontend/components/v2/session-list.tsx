import { cn } from "@/lib/utils";
import { clockShort, duration, responseSeconds, stageLabel } from "@/lib/format";
import type { Session } from "@/lib/types";
import { OutcomeChip } from "./chips";
import { paceOf, paceText } from "@/lib/v2/view";

// Sessions, needs-a-person first, then newest. Each row: id, customer, route, stage, response time, outcome.
export function SessionList({ sessions, selectedId, onSelect }: { sessions: Session[]; selectedId: number | null; onSelect: (id: number) => void }) {
  return (
    <ul className="flex flex-col gap-1.5" aria-label="Sessions">
      {sessions.map((s) => {
        const sec = responseSeconds(s);
        const pace = sec === null ? null : paceOf(sec);
        const label = [
          `Session #${s.id}, ${s.customer}`,
          s.needs_human && "needs a person",
          stageLabel[s.stage],
          sec === null ? "no quote yet" : `quoted after ${duration(sec)}, ${paceText[pace!]}`,
          `outcome ${s.outcome}`,
        ].filter(Boolean).join(", ");
        return (
          <li key={s.id}>
            <button
              type="button"
              onClick={() => onSelect(s.id)}
              aria-label={label}
              aria-current={s.id === selectedId ? "true" : undefined}
              className={cn(
                "bg-(--v2-surface) border-(--v2-rule) w-full rounded-md border px-3 py-2 text-left transition-colors hover:bg-(--v2-surface-2)",
                s.id === selectedId && "ring-2 ring-(--v2-open)",
                s.needs_human && "border-l-4 border-l-(--v2-signal)",
              )}
            >
              <span className="flex items-center gap-2">
                <span className="text-(--v2-ink-2) font-mono text-xs">#{s.id}</span>
                <span className="min-w-0 flex-1 truncate font-semibold">{s.customer}</span>
                <OutcomeChip outcome={s.outcome} />
              </span>
              <span className="mt-1 flex items-center gap-2 text-sm">
                <span className="text-(--v2-ink-2)">{s.rfq ? `${s.rfq.origin} → ${s.rfq.destination}` : clockShort(s.received_at)}</span>
                <span className="border-(--v2-rule) rounded-sm border px-1.5 text-xs font-semibold">{stageLabel[s.stage]}</span>
                {s.needs_human && <span className="text-(--v2-signal-text) text-xs font-bold">Needs a person</span>}
                <span
                  className={cn(
                    "ml-auto font-mono tabular-nums",
                    pace === "late" && "text-(--v2-late-text) font-bold",
                    pace === "zero" && "text-(--v2-signal-text) font-bold",
                  )}
                >
                  {sec === null ? "–" : duration(sec)}
                  {pace && pace !== "ok" && <span className="ml-1 text-xs">{pace === "late" ? "late" : "zero"}</span>}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
