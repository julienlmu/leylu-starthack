import { Search, UserRound } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { clock, duration, responseSeconds, stageStyle } from "@/lib/format";
import type { Session, Stage } from "@/lib/types";

const STAGES: (Stage | "all" | "human")[] = ["all", "human", "new", "pricing", "quoted", "booked", "tracking", "failed"];

type Props = {
  sessions: Session[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  query: string;
  onQuery: (q: string) => void;
  filter: Stage | "all" | "human";
  onFilter: (f: Stage | "all" | "human") => void;
};

export function SessionList({ sessions, selectedId, onSelect, query, onQuery, filter, onFilter }: Props) {
  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b p-3">
        <div className="relative">
          <Search className="text-muted-foreground absolute top-2.5 left-2.5 size-4" />
          <Input
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder="Customer, route, reference, #id…"
            className="pl-8"
          />
        </div>
        <div className="flex flex-wrap gap-1">
          {STAGES.map((s) => (
            <button
              key={s}
              onClick={() => onFilter(s)}
              className={cn(
                "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                filter === s ? "bg-foreground text-background border-foreground" : "hover:bg-muted",
              )}
            >
              {s === "human" ? "needs a person" : s}
            </button>
          ))}
        </div>
      </div>

      <ul className="flex-1 overflow-y-auto">
        {sessions.length === 0 && <li className="text-muted-foreground p-6 text-center text-sm">No sessions match.</li>}
        {sessions.map((s) => {
          const rt = responseSeconds(s);
          return (
            <li key={s.id}>
              <button
                onClick={() => onSelect(s.id)}
                className={cn(
                  "w-full border-b px-3 py-2.5 text-left transition-colors",
                  s.id === selectedId ? "bg-muted" : "hover:bg-muted/50",
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground font-mono text-xs">#{s.id}</span>
                  <span className="flex-1 truncate text-sm font-medium">{s.customer}</span>
                  {s.needs_human && <UserRound className="size-4 text-red-600" aria-label="needs a person" />}
                  <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-medium", stageStyle[s.stage])}>{s.stage}</span>
                </div>
                <div className="text-muted-foreground mt-1 flex items-center gap-2 font-mono text-xs">
                  <span>{s.rfq ? `${s.rfq.origin} → ${s.rfq.destination}` : "extracting…"}</span>
                  {s.rfq && <span>· {s.rfq.ask}</span>}
                  <span className="ml-auto">{clock(s.received_at)}</span>
                  {rt !== null && <span className={rt <= 120 ? "text-emerald-700" : "text-amber-700"}>{duration(rt)}</span>}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
