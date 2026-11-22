"use client";
// v2 proposal: one screen for the jury. Read-only (no pause/resume/reply here); the live UI stays at "/".
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useLiveData } from "@/lib/live";
import { Round } from "@/components/v2/round";
import { SessionList } from "@/components/v2/session-list";
import { Detail } from "@/components/v2/detail";
import { KpiStrip } from "@/components/v2/kpi-strip";

const newest = (a: { received_at: string }, b: { received_at: string }) => Date.parse(b.received_at) - Date.parse(a.received_at);

export default function V2Page() {
  const data = useLiveData();
  const [picked, setPicked] = useState<number | null>(null);
  useEffect(() => {
    // Deep link like the live UI: /v2?s=17 opens session 17.
    const id = Number(new URLSearchParams(window.location.search).get("s"));
    if (Number.isInteger(id) && id > 0) setPicked(id);
  }, []);

  const byTime = useMemo(() => [...(data?.sessions ?? [])].sort(newest), [data]);
  const list = useMemo(() => [...byTime].sort((a, b) => Number(b.needs_human) - Number(a.needs_human)), [byTime]);
  // Nothing picked: follow the newest RFQ, so the round view moves on its own during the demo.
  const selected = byTime.find((s) => s.id === picked) ?? byTime[0] ?? null;

  const loadEvents = data?.loadEvents;
  useEffect(() => {
    if (loadEvents && selected) loadEvents(selected.id);
  }, [loadEvents, selected?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const events = useMemo(
    () => (data?.events ?? []).filter((e) => e.session_id === selected?.id).sort((a, b) => Date.parse(a.at) - Date.parse(b.at)),
    [data, selected?.id],
  );

  return (
    <div className="flex h-screen flex-col gap-3 p-3">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <h1 className="font-condensed text-2xl font-bold">Leylü Forwarder</h1>
        <span className="text-(--v2-ink-2) flex items-center gap-1.5 text-sm" aria-live="polite">
          <span aria-hidden className={`size-2 rounded-full ${data?.connected ? "bg-(--v2-done)" : "bg-(--v2-rule)"}`} />
          {!data ? "Loading" : data.live ? (data.connected ? "Live" : "Reconnecting") : "Mock data"}
        </span>
        <span className="text-(--v2-ink-2) text-xs">
          Proposal ·{" "}
          <Link href="/" className="underline">
            current UI
          </Link>
        </span>
        <div className="ml-auto">
          <KpiStrip sessions={byTime} />
        </div>
      </header>

      {selected ? <Round session={selected} events={events} /> : <p className="text-(--v2-ink-2)">{data ? "No RFQ yet." : "Loading…"}</p>}

      <div className="grid min-h-0 flex-1 grid-cols-[22rem_minmax(0,1fr)] gap-3">
        <nav aria-label="Sessions" className="min-h-0 overflow-y-auto pr-1">
          <Legend />
          <SessionList sessions={list} selectedId={selected?.id ?? null} onSelect={setPicked} />
        </nav>
        <main className="min-h-0 overflow-y-auto">{selected && <Detail session={selected} events={events} />}</main>
      </div>
    </div>
  );
}

function Legend() {
  const items = [
    ["bg-(--v2-won)", "Won"],
    ["bg-(--v2-open)", "Open"],
    ["bg-(--v2-lost)", "Lost"],
    ["bg-(--v2-expired)", "Expired"],
    ["bg-(--v2-late)", "Late, over 2:00"],
  ];
  return (
    <ul aria-label="Legend" className="text-(--v2-ink-2) mb-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
      {items.map(([c, t]) => (
        <li key={t} className="flex items-center gap-1">
          <span aria-hidden className={`size-2.5 rounded-sm ${c}`} />
          {t}
        </li>
      ))}
    </ul>
  );
}
