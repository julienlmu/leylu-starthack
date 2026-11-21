"use client";

import { useEffect, useMemo, useState } from "react";
import { Plane } from "lucide-react";
import { SessionDetail } from "@/components/session-detail";
import { SessionList } from "@/components/session-list";
import { loadData, type Data } from "@/lib/api";
import type { Session, Stage } from "@/lib/types";

const matches = (s: Session, q: string) => {
  if (!q) return true;
  const hay = [
    `#${s.id}`,
    s.customer,
    s.thread_id,
    s.rfq?.origin,
    s.rfq?.destination,
    s.rfq?.customer_reference,
    s.rfq?.commodity,
    s.quote?.carrier,
    s.booking?.confirmation,
  ]
    .join(" ")
    .toLowerCase();
  return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w));
};

export default function SessionsPage() {
  const [data, setData] = useState<Data | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Stage | "all" | "human">("all");

  useEffect(() => {
    loadData().then(setData);
  }, []);

  const sessions = useMemo(
    () =>
      (data?.sessions ?? [])
        .filter((s) => filter === "all" || (filter === "human" ? s.needs_human : s.stage === filter))
        .filter((s) => matches(s, query))
        .sort((a, b) => Date.parse(b.received_at) - Date.parse(a.received_at)),
    [data, filter, query],
  );

  const selected = sessions.find((s) => s.id === selectedId) ?? sessions[0] ?? null;
  const events = (data?.events ?? []).filter((e) => e.session_id === selected?.id).sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  const humanCount = data?.sessions.filter((s) => s.needs_human).length ?? 0;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b px-4 py-2.5">
        <Plane className="size-5" />
        <h1 className="font-semibold">Leylü Forwarder</h1>
        <span className="text-muted-foreground text-sm">Sessions</span>
        <div className="ml-auto flex items-center gap-3 text-xs">
          {humanCount > 0 && (
            <button onClick={() => setFilter("human")} className="rounded-full bg-red-100 px-2.5 py-0.5 font-medium text-red-800">
              {humanCount} {humanCount === 1 ? "needs" : "need"} a person
            </button>
          )}
          {data && (
            <span className="flex items-center gap-1.5">
              <span className={`size-2 rounded-full ${data.live ? "bg-emerald-500" : "bg-amber-500"}`} />
              {data.live ? "live backend" : "mock data"}
            </span>
          )}
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-[360px_1fr]">
        <aside className="min-h-0 border-r">
          <SessionList
            sessions={sessions}
            selectedId={selected?.id ?? null}
            onSelect={setSelectedId}
            query={query}
            onQuery={setQuery}
            filter={filter}
            onFilter={setFilter}
          />
        </aside>
        <main className="min-h-0 overflow-y-auto">
          {!data && <p className="text-muted-foreground p-6 text-sm">Loading…</p>}
          {data && !selected && <p className="text-muted-foreground p-6 text-sm">No session selected.</p>}
          {selected && <SessionDetail session={selected} events={events} />}
        </main>
      </div>
    </div>
  );
}
