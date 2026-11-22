"use client";

import { forwardRef } from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { STAGES, clockShort, duration, moneyShort, pace, pieceCount, responseSeconds, shortCarrier, stageLabel } from "@/lib/format";
import type { Session, Stage } from "@/lib/types";

export type Filter = Stage | "all" | "person" | "spam";

type Props = {
  sessions: Session[];
  counts: Record<Filter, number>;
  selectedId: number | null;
  onSelect: (id: number) => void;
  query: string;
  onQuery: (q: string) => void;
  filter: Filter;
  onFilter: (f: Filter) => void;
  loading: boolean;
  reasons: Record<number, string>;
  spam: Record<number, string>; // session id → why the agent closed it as spam
};

export const SessionRack = forwardRef<HTMLInputElement, Props>(function SessionRack(
  { sessions, counts, selectedId, onSelect, query, onQuery, filter, onFilter, loading, reasons, spam },
  searchRef,
) {
  return (
    <section aria-label="Sessions" id="sessions" className="@container flex min-h-0 flex-1 flex-col">
      <div className="border-rule flex flex-col gap-2.5 border-b px-3 pt-3 pb-3">
        <label className="relative block" data-guide="search">
          <span className="sr-only">Search sessions</span>
          <Search className="text-ink-3 pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" aria-hidden />
          <input
            ref={searchRef}
            type="search"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                onQuery("");
                e.currentTarget.blur();
              }
            }}
            placeholder="Customer, route, ref, #id, carrier, AWB"
            className="border-rule-strong bg-paper text-ink placeholder:text-ink-3 focus-visible:border-[var(--st-new)] h-10 w-full rounded-sm border pr-16 pl-9 text-[0.9375rem] outline-none [&::-webkit-search-cancel-button]:hidden"
          />
          {query ? (
            <button
              type="button"
              onClick={() => onQuery("")}
              className="text-ink-2 hover:text-ink absolute top-1/2 right-2 flex size-7 -translate-y-1/2 items-center justify-center rounded-sm"
              aria-label="Clear search"
            >
              <X className="size-4" />
            </button>
          ) : (
            <kbd className="border-rule text-ink-3 font-condensed pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 rounded-[3px] border px-1.5 text-xs font-semibold">
              /
            </kbd>
          )}
        </label>

        <div role="group" aria-label="Filter sessions" className="grid grid-cols-4 gap-1" data-guide="filters">
          <Chip active={filter === "person"} onClick={() => onFilter("person")} count={counts.person} person className="col-span-4">
            Needs a person
          </Chip>
          <Chip active={filter === "all"} onClick={() => onFilter("all")} count={counts.all}>
            All
          </Chip>
          {STAGES.map((st) => (
            <Chip key={st} active={filter === st} onClick={() => onFilter(st)} count={counts[st]} stage={st}>
              {stageLabel[st]}
            </Chip>
          ))}
          <Chip active={filter === "spam"} onClick={() => onFilter("spam")} count={counts.spam} spam>
            Spam
          </Chip>
        </div>
      </div>

      <div className="thin-scroll min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        {loading ? (
          <ul className="flex flex-col gap-2 py-3 pr-5 pl-3" aria-hidden>
            {Array.from({ length: 6 }, (_, i) => (
              <li key={i} className="bg-paper/70 h-[4.5rem] animate-pulse rounded-sm" />
            ))}
          </ul>
        ) : sessions.length === 0 ? (
          <EmptyRack query={query} filter={filter} onReset={() => {
              onQuery("");
              onFilter("all");
            }} />
        ) : (
          <ul className="flex flex-col gap-2 py-3 pr-5 pl-3" data-guide="strips">
            {sessions.map((s) => (
              <li key={s.id}>
                <SessionStrip session={s} reason={reasons[s.id]} spam={spam[s.id]} selected={s.id === selectedId} onSelect={() => onSelect(s.id)} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="border-rule text-ink-3 hidden border-t px-4 py-2 text-xs md:block">
        <kbd className="font-condensed font-semibold">J</kbd> / <kbd className="font-condensed font-semibold">K</kbd> next and
        previous session · <kbd className="font-condensed font-semibold">/</kbd> search
      </p>
    </section>
  );
});

function Chip({
  active,
  onClick,
  count,
  children,
  stage,
  person,
  spam,
  className,
}: {
  active: boolean;
  onClick: () => void;
  count: number;
  children: React.ReactNode;
  stage?: Stage;
  person?: boolean;
  spam?: boolean;
  className?: string;
}) {
  const alert = person && count > 0;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      data-stage={stage}
      data-spam={spam || undefined}
      className={cn(
        "flex h-7 min-w-0 items-center gap-1 rounded-sm border px-1.5 text-[0.75rem] @[26rem]:gap-1.5 @[26rem]:px-2 font-medium transition-colors duration-150 @[24rem]:text-[0.8125rem]",
        person && "h-8 text-[0.875rem] font-semibold @[24rem]:text-[0.875rem]",
        active
          ? "border-ink bg-ink text-paper"
          : alert
            ? "border-signal bg-signal-wash text-signal-text hover:bg-paper"
            : "border-rule-strong bg-paper/60 text-ink-2 hover:bg-paper hover:text-ink",
        count === 0 && !active && "opacity-60",
        className,
      )}
    >
      {(stage || spam) && <span className="hidden size-2.5 shrink-0 rounded-[2px] bg-[var(--holder)] @[26rem]:block" aria-hidden />}
      {person && <span className={cn("size-2.5 rounded-[2px]", alert || active ? "bg-signal" : "bg-ink-3")} aria-hidden />}
      <span className="truncate">{children}</span>
      <span className={cn("font-condensed ml-auto font-semibold tabular-nums", active ? "text-paper/80" : "text-ink-3", alert && !active && "text-signal-text")}>
        {count}
      </span>
    </button>
  );
}

function SessionStrip({
  session: s,
  reason,
  spam,
  selected,
  onSelect,
}: {
  session: Session;
  reason?: string;
  spam?: string;
  selected: boolean;
  onSelect: () => void;
}) {
  const sec = responseSeconds(s);
  const closed = s.outcome === "lost" || s.outcome === "expired";
  const price = s.quote ?? null;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={selected ? "true" : undefined}
      data-strip={s.id}
      data-stage={s.stage}
      data-person={s.needs_human}
      data-spam={spam !== undefined || undefined}
      className={cn(
        "group bg-paper text-ink relative grid w-full grid-cols-[3.5rem_minmax(0,1fr)_5rem] text-left @[26rem]:grid-cols-[3.5rem_minmax(0,1fr)_3.5rem_5rem]",
        "rounded-sm shadow-[0_1px_0_oklch(0.2_0.03_258/0.08),0_1px_3px_oklch(0.2_0.03_258/0.06)]",
        "transition-[transform,box-shadow] duration-200 ease-out",
        // A strip that needs a person is cocked out of line, as a controller flags one for action.
        s.needs_human ? "cocked translate-x-3" : "hover:translate-x-0.5",
        selected && "ring-ink z-10 shadow-[0_6px_16px_-4px_oklch(0.2_0.03_258/0.28)] ring-2",
      )}
    >
      <span
        className={cn(
          "relative flex flex-col items-center justify-center gap-1 rounded-l-sm bg-[var(--holder)] text-[var(--holder-ink)]",
          s.paused && "hatch",
        )}
      >
        <span className="font-condensed text-[1.375rem] leading-none font-bold tabular-nums">{s.id}</span>
        <span className="font-condensed text-[0.625rem] leading-none font-semibold tracking-[0.08em] uppercase">
          {spam !== undefined ? "Spam" : stageLabel[s.stage]}
        </span>
      </span>

      <span className="flex min-w-0 flex-col justify-center gap-1 px-3 py-2.5">
        <span className="truncate text-[0.9375rem] leading-tight font-semibold" title={s.customer}>
          {s.customer}
        </span>
        <span className="text-ink-2 flex min-w-0 items-baseline gap-1.5 text-[0.8125rem] leading-tight">
          {spam !== undefined ? (
            <span className="text-ink-3 truncate" title={spam}>Spam: {spam}</span>
          ) : s.rfq ? (
            <>
              <span className="font-condensed text-ink shrink-0 text-sm font-bold tracking-wide">
                {s.rfq.origin}–{s.rfq.destination}
              </span>
              {sec !== null && (
                <span className={cn("shrink-0 font-semibold tabular-nums @[26rem]:hidden", pace(sec) === "on-target" ? "text-ok" : "text-late-text")}>
                  {duration(sec)}
                </span>
              )}
              <span className="truncate">
                {pieceCount(s)} pcs · {s.rfq.ask}
                {!s.needs_human && s.rfq.dangerous_goods && <span className="text-signal-text font-semibold"> · DG</span>}
                {!s.needs_human && s.paused && <span className="font-semibold"> · paused</span>}
              </span>
            </>
          ) : (
            <span className="text-ink-3 italic">reading the mail…</span>
          )}
        </span>
        {s.needs_human && reason && (
          <span className="text-signal-text text-[0.8125rem] leading-snug font-semibold">
            {reason}
            {s.paused && <span className="text-ink-2 font-medium"> · paused</span>}
          </span>
        )}
      </span>

      <span className="border-rule hidden flex-col justify-center gap-1 border-l px-2 py-2.5 @[26rem]:flex">
        <span className="caption">{clockShort(s.received_at)}</span>
        <span
          className={cn(
            "font-condensed text-lg leading-none font-bold tabular-nums",
            sec === null && "text-ink-3",
            sec !== null && pace(sec) === "on-target" && "text-ok",
            sec !== null && pace(sec) !== "on-target" && "text-late-text",
          )}
          title={sec === null ? "No quote sent yet" : `Quote sent ${duration(sec)} after the RFQ arrived`}
        >
          {sec === null ? "–:––" : duration(sec)}
        </span>
      </span>

      <span className="border-rule flex flex-col items-end justify-center gap-1 border-l px-2.5 py-2.5">
        {spam !== undefined ? (
          <span className="caption text-ink-2 font-bold">no reply</span>
        ) : closed ? (
          <span className="caption text-ink-2 font-bold">{s.outcome}</span>
        ) : (
          <span className="caption max-w-full truncate">{price ? shortCarrier(price.carrier) : "no quote"}</span>
        )}
        <span className={cn("text-[0.9375rem] leading-none font-semibold tabular-nums", (!price || closed) && "text-ink-3", closed && price && "line-through decoration-1")}>
          {price ? moneyShort(price.total, price.currency) : "–"}
        </span>
      </span>
    </button>
  );
}

function EmptyRack({ query, filter, onReset }: { query: string; filter: Filter; onReset: () => void }) {
  const what = query
    ? `Nothing matches “${query.trim()}”${filter === "all" ? "" : " in this filter"}.`
    : filter === "person"
      ? "No session needs a person right now."
      : filter === "spam"
        ? "No spam caught yet."
        : "No sessions in this stage yet.";
  return (
    <div className="flex flex-col items-start gap-3 p-6">
      <p className="text-ink font-semibold">{what}</p>
      <p className="text-ink-2 text-sm">
        {filter === "person" && !query
          ? "The agent is handling every request on its own. Sessions it cannot answer land here."
          : "Search looks at customer, route (MUC JFK), reference, #id, carrier and booking or AWB number."}
      </p>
      <button type="button" onClick={onReset} className="border-rule-strong bg-paper hover:bg-paper-2 h-8 rounded-sm border px-3 text-sm font-medium">
        Show all sessions
      </button>
    </div>
  );
}
