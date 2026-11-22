"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SessionDetail } from "@/components/session-detail";
import { SessionRack, type Filter } from "@/components/session-rack";
import { SimpleView } from "@/components/simple-view";
import { TopBar } from "@/components/top-bar";
import { useLiveData } from "@/lib/live";
import { STAGES, matches, maybeSpam, responseSeconds, spamReasons } from "@/lib/format";
import { VIEWS, usePref } from "@/lib/prefs";

const byNewest = (a: { received_at: string }, b: { received_at: string }) => Date.parse(b.received_at) - Date.parse(a.received_at);

export default function SessionsPage() {
  const data = useLiveData(); // F2: initial load + live stream (or demo replay on mock data)
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [view, setView] = usePref("leylu-view", "detailed", VIEWS);
  const [composeFor, setComposeFor] = useState<number | null>(null); // "Reply myself" from the simple view
  const searchRef = useRef<HTMLInputElement>(null);
  const detailRef = useRef<HTMLElement>(null);

  useEffect(() => {
    // Deep link: /?s=17 opens session 17 (handy for sharing a session with a teammate).
    const id = Number(new URLSearchParams(window.location.search).get("s"));
    if (Number.isInteger(id) && id > 0) setSelectedId(id);
  }, []);

  const all = useMemo(() => [...(data?.sessions ?? [])].sort(byNewest), [data]);

  const spam = useMemo(() => spamReasons(data?.events ?? []), [data]);
  const isSpam = useCallback((s: { id: number }) => spam[s.id] !== undefined, [spam]);

  const counts = useMemo(() => {
    const c = {
      all: all.length,
      person: all.filter((s) => s.needs_human && !isSpam(s)).length,
      spam: all.filter(isSpam).length,
    } as Record<Filter, number>;
    for (const st of STAGES) c[st] = all.filter((s) => s.stage === st && !isSpam(s)).length;
    return c;
  }, [all, isSpam]);

  const sessions = useMemo(
    () =>
      all
        .filter((s) =>
          filter === "all"
            ? true
            : filter === "spam"
              ? isSpam(s)
              : !isSpam(s) && (filter === "person" ? s.needs_human : s.stage === filter),
        )
        .filter((s) => matches(s, query)),
    [all, filter, query, isSpam],
  );

  // Default to the first session that needs a person: that is why the operator opened the screen.
  const selected =
    sessions.find((s) => s.id === selectedId) ?? sessions.find((s) => s.needs_human) ?? sessions[0] ?? null;
  // Event history only for what the screen shows: the open session and the flagged ones (their reason line).
  const loadEvents = data?.loadEvents;
  // ...and the closed, unread ones, which may be spam (their "Spam:" routed event says so).
  const flaggedIds = all.filter((s) => s.needs_human || maybeSpam(s)).map((s) => s.id).join(",");
  useEffect(() => {
    if (!loadEvents) return;
    if (selected) loadEvents(selected.id);
    flaggedIds.split(",").filter(Boolean).forEach((id) => loadEvents(Number(id)));
  }, [loadEvents, selected?.id, flaggedIds]); // eslint-disable-line react-hooks/exhaustive-deps

  const events = useMemo(
    () => (data?.events ?? []).filter((e) => e.session_id === selected?.id).sort((a, b) => Date.parse(a.at) - Date.parse(b.at)),
    [data, selected?.id],
  );

  // Why each flagged session needs a person, from its latest needs_human step.
  const reasons = useMemo(() => {
    const r: Record<number, string> = {};
    for (const e of data?.events ?? []) {
      if (e.kind === "needs_human" && e.session_id !== null) r[e.session_id] = e.text.replace(/:\s*needs a person\.?$/i, "");
    }
    return r;
  }, [data]);

  const tally = useMemo(() => {
    if (!data) return null;
    const rfqs = all.filter((s) => !isSpam(s));
    const times = rfqs.map(responseSeconds).filter((v): v is number => v !== null).sort((a, b) => a - b);
    return {
      total: rfqs.length,
      quoted: rfqs.filter((s) => s.quote).length,
      medianResponse: times.length ? times[Math.floor(times.length / 2)] : null,
      llmCost: all.reduce((sum, s) => sum + s.llm_cost_usd, 0),
    };
  }, [data, all, isSpam]);

  const select = useCallback((id: number) => {
    setSelectedId(id);
    setComposeFor(null);
    detailRef.current?.scrollTo({ top: 0 });
    window.history.replaceState(null, "", `?s=${id}`);
  }, []);

  // J/K (or arrows) walk the rack in sequence; "/" jumps to search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (view === "simple") return; // the simple view has no rack to walk
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
        return;
      }
      const step = e.key === "j" || e.key === "ArrowDown" ? 1 : e.key === "k" || e.key === "ArrowUp" ? -1 : 0;
      if (!step || !sessions.length) return;
      e.preventDefault();
      const i = selected ? sessions.findIndex((s) => s.id === selected.id) : -1;
      const next = sessions[Math.min(sessions.length - 1, Math.max(0, i + step))];
      select(next.id);
      document.querySelector(`[data-strip="${next.id}"]`)?.scrollIntoView({ block: "nearest" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sessions, selected, select, view]);

  const togglePersonQueue = () => {
    setView("detailed");
    setFilter((f) => (f === "person" ? "all" : "person"));
  };
  // From the simple view into one request's full record (optionally with the reply box open).
  const openDetailed = (id: number, compose = false) => {
    setQuery("");
    setFilter("all");
    setView("detailed");
    select(id);
    if (compose) setComposeFor(id);
  };

  return (
    <div className="flex min-h-screen flex-col md:h-screen md:min-h-0">
      <TopBar
        active="sessions"
        loading={!data}
        live={data?.live ?? false}
        connected={data?.connected ?? false}
        personCount={counts.person}
        personActive={filter === "person"}
        onPersonQueue={togglePersonQueue}
        tally={tally}
        view={view}
        onView={setView}
      />

      {view === "simple" ? (
        <main className="bg-paper-2 thin-scroll min-h-0 flex-1 md:overflow-y-auto" aria-busy={!data}>
          <SimpleView
            sessions={all.filter((s) => !isSpam(s))}
            loading={!data}
            reasons={reasons}
            onOpen={(id) => openDetailed(id)}
            onReply={(id) => openDetailed(id, true)}
          />
        </main>
      ) : (

      <div className="flex min-h-0 flex-1 flex-col md:grid md:grid-cols-[21rem_minmax(0,1fr)] xl:grid-cols-[28rem_minmax(0,1fr)]">
        <aside className="bg-board border-rule flex max-h-[26rem] min-h-0 flex-col border-b md:max-h-none md:border-r md:border-b-0">
          <SessionRack
            ref={searchRef}
            sessions={sessions}
            counts={counts}
            selectedId={selected?.id ?? null}
            onSelect={select}
            query={query}
            onQuery={setQuery}
            filter={filter}
            onFilter={setFilter}
            loading={!data}
            reasons={reasons}
            spam={spam}
          />
        </aside>

        <main ref={detailRef} className="bg-paper-2 thin-scroll @container min-h-0 flex-1 md:overflow-y-auto" aria-live="polite" aria-busy={!data}>
          {!data && <DetailSkeleton />}
          {data && !selected && (
            <div className="flex h-full min-h-64 flex-col items-start justify-center gap-2 px-8">
              <p className="text-ink text-lg font-semibold">No session to show</p>
              <p className="text-ink-2 max-w-md">The rack is empty for this search or filter. Clear it to see every session again.</p>
            </div>
          )}
          {selected && data && (
            <SessionDetail
              session={selected}
              events={events}
              since={data.since}
              live={data.live}
              apply={data.apply}
              applySession={data.applySession}
              spam={spam[selected.id]}
              compose={composeFor === selected.id}
            />
          )}
        </main>
      </div>
      )}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-5 px-5 pt-6 md:px-8" aria-hidden>
      <div className="flex items-end gap-5">
        <div className="bg-paper h-16 w-20 animate-pulse rounded-sm" />
        <div className="bg-paper h-8 w-72 animate-pulse rounded-sm" />
      </div>
      <div className="bg-paper h-9 animate-pulse rounded-sm" />
      <div className="bg-paper h-36 animate-pulse rounded-sm" />
      <div className="bg-paper h-24 animate-pulse rounded-sm" />
    </div>
  );
}
