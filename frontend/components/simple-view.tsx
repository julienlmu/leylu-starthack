"use client";
// The calm view for a first-time user: what needs a person, what is being answered, what is done.
// Internals (event log, bids, gate wording) stay in the detailed view behind "Show details".
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { ArrowRight, ChevronDown, MessageCircleQuestion, Package, Pause, Play, Search, SquarePen, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { setPaused } from "@/components/intervene-bar";
import { cn } from "@/lib/utils";
import { duration, isOurs, mailOf, matches, moneyShort, pace, responseSeconds, shortCarrier, transit } from "@/lib/format";
import type { LiveData } from "@/lib/live";
import type { Event, Session } from "@/lib/types";

type Props = {
  sessions: Session[]; // newest first, spam included (hidden unless its chip is on)
  spam: Record<number, string>; // session id → why the agent closed it as spam
  events: Event[];
  loading: boolean;
  reasons: Record<number, string>;
  live: boolean;
  apply?: LiveData["apply"];
  applySession?: LiveData["applySession"];
  loadEvents?: (id: number) => void;
  onOpen: (id: number, section?: string) => void; // section = a [data-guide] in the detailed view
  onReply: (id: number) => void;
};

type Chip = "needs" | "working" | "done" | "spam";
type Ctx = Pick<Props, "live" | "apply" | "applySession" | "onOpen" | "onReply" | "loadEvents"> & {
  mails: (id: number) => { inMail?: string; outMail?: string };
};

const DAY_MS = 24 * 3600 * 1000;

// One plain status per request.
function status(s: Session): { word: string; stage: string; person?: boolean } {
  if (s.needs_human) return { word: "Needs you", stage: "new", person: true };
  if (s.stage === "new" || s.stage === "pricing") return { word: "Being answered", stage: "pricing" };
  if (s.stage === "quoted" && s.outcome === "open") return { word: "Quote sent, waiting for the customer", stage: "quoted" };
  if (s.booking || s.stage === "booked" || s.stage === "tracking") return { word: "Booked", stage: "booked" };
  if (s.stage === "failed") return { word: "Not answered", stage: "failed" };
  return { word: s.outcome === "won" ? "Done, won" : "Done, closed", stage: "done" };
}

const STEPS = ["Read", "Priced", "Quoted", "Booked"] as const;
// How many of the four steps are done.
const stepsDone = (s: Session, priced: boolean) =>
  s.booking || s.stage === "booked" || s.stage === "tracking" ? 4 : s.quote ? 3 : priced || s.bids.length ? 2 : s.rfq ? 1 : 0;

const oneLine = (text: string) => text.replace(/\s+/g, " ").trim();

export function SimpleView({ sessions, spam, events, loading, reasons, live, apply, applySession, loadEvents, onOpen, onReply }: Props) {
  const [chip, setChip] = useState<Chip | null>(null);
  const [query, setQuery] = useState("");

  // Latest mail each way, and whether a price was collected, per session (from the events the page holds).
  const perSession = useMemo(() => {
    const m: Record<number, { inMail?: string; outMail?: string; priced?: boolean }> = {};
    for (const e of [...events].sort((a, b) => Date.parse(a.at) - Date.parse(b.at))) {
      if (e.session_id === null) continue;
      const r = (m[e.session_id] ??= {});
      if (e.kind === "priced" || e.kind === "bid") r.priced = true;
      const mail = mailOf(e);
      if (mail) r[isOurs(e) ? "outMail" : "inMail"] = oneLine(mail.body);
    }
    return m;
  }, [events]);

  const groups = useMemo(() => {
    const rfqs = sessions.filter((s) => spam[s.id] === undefined);
    const finished = rfqs.filter((s) => !s.needs_human && s.stage !== "new" && s.stage !== "pricing");
    // "Today" = the 24 hours up to the newest finished request (the mock night is not today's date, and the
    // demo replay's request arrives "now").
    const newest = finished.length ? Date.parse(finished[0].received_at) : 0;
    return {
      needs: rfqs.filter((s) => s.needs_human),
      working: rfqs.filter((s) => !s.needs_human && (s.stage === "new" || s.stage === "pricing")),
      done: finished.filter((s) => newest - Date.parse(s.received_at) < DAY_MS),
      spam: sessions.filter((s) => spam[s.id] !== undefined),
    };
  }, [sessions, spam]);

  const shown = (k: Chip) => (chip === k || (chip === null && k !== "spam") ? groups[k].filter((s) => matches(s, query)) : null);
  const needs = shown("needs");
  const working = shown("working");
  const done = shown("done");
  const spamRows = shown("spam");

  // Cards show mail previews: make sure their history is loaded (live mode; mock data has it all).
  const cardIds = [...(needs ?? []), ...(working ?? [])].map((s) => s.id).join(",");
  useEffect(() => {
    cardIds.split(",").filter(Boolean).forEach((id) => loadEvents?.(Number(id)));
  }, [cardIds, loadEvents]);

  if (loading) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-5 pt-8" aria-hidden>
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="bg-paper h-24 animate-pulse rounded-sm" />
        ))}
      </div>
    );
  }

  const ctx: Ctx = { live, apply, applySession, onOpen, onReply, loadEvents, mails: (id) => perSession[id] ?? {} };
  const priced = (id: number) => !!perSession[id]?.priced;
  const noMatch = query.trim() ? "No request matches this search." : undefined;
  const CHIPS: { key: Chip; label: string }[] = [
    { key: "needs", label: "Needs you" },
    { key: "working", label: "Being answered" },
    { key: "done", label: "Done today" },
    { key: "spam", label: "Spam" },
  ];

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-10 px-4 pt-8 pb-16 sm:px-5 md:px-8">
      <header className="flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <h1 className="text-ink text-[1.75rem] leading-tight font-semibold tracking-tight">
            {groups.needs.length === 0
              ? "Nothing needs you right now"
              : groups.needs.length === 1
                ? "One request needs you"
                : `${groups.needs.length} requests need you`}
          </h1>
          <p className="text-ink-2 max-w-2xl">
            The agent answers every air-freight request on its own. It only asks you when it can&apos;t be sure. Open a request
            with &ldquo;Show details&rdquo; to see everything it did.
          </p>
        </div>

        <div role="group" aria-label="Show only" data-guide="simple-chips" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {CHIPS.map(({ key, label }) => {
            const on = chip === key;
            const alert = key === "needs" && groups.needs.length > 0;
            return (
              <button
                key={key}
                type="button"
                aria-pressed={on}
                onClick={() => setChip(on ? null : key)}
                className={cn(
                  "flex flex-col items-start gap-0.5 rounded-sm border px-3.5 py-2.5 text-left transition-colors",
                  on ? "border-ink bg-ink text-paper" : "border-rule bg-paper text-ink hover:border-rule-strong",
                  alert && !on && "border-signal border-l-4",
                )}
              >
                <span className={cn("text-2xl leading-none font-semibold tabular-nums", alert && !on && "text-signal-text")}>
                  {groups[key].length}
                </span>
                <span className={cn("text-sm font-medium", on ? "text-paper" : "text-ink-2")}>{label}</span>
              </button>
            );
          })}
        </div>

        <label className="relative block" data-guide="simple-search">
          <span className="sr-only">Search requests</span>
          <Search className="text-ink-3 pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2" aria-hidden />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && setQuery("")}
            placeholder="Customer, route (MUC JFK) or booking ref"
            className="border-rule-strong bg-paper text-ink placeholder:text-ink-3 h-11 w-full rounded-sm border pr-11 pl-9 text-[0.9375rem] outline-none focus-visible:border-[var(--st-new)] [&::-webkit-search-cancel-button]:hidden"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="text-ink-2 hover:text-ink absolute top-1/2 right-2 flex size-8 -translate-y-1/2 items-center justify-center rounded-sm"
              aria-label="Clear search"
            >
              <X className="size-4" />
            </button>
          )}
        </label>
      </header>

      {needs && (
        <Group title="Needs you" guide="simple-needs" empty={noMatch ?? "All clear. Requests the agent can't answer alone show up here."}>
          {needs.map((s) => (
            <Card key={s.id} session={s} reason={reasons[s.id]} priced={priced(s.id)} ctx={ctx} />
          ))}
        </Group>
      )}

      {working && (
        <Group title="Being answered" guide="simple-working" empty={noMatch ?? "No request is being priced right now."}>
          {working.map((s) => (
            <Card key={s.id} session={s} priced={priced(s.id)} ctx={ctx} />
          ))}
        </Group>
      )}

      {done && (
        <Group title="Done today" guide="simple-done" empty={noMatch ?? "Nothing answered yet today."} compact>
          {done.map((s) => (
            <Row key={s.id} session={s} ctx={ctx} />
          ))}
        </Group>
      )}

      {spamRows && (
        <Group title="Spam" guide="simple-spam" empty={noMatch ?? "No spam: every mail was a real request."} compact>
          {spamRows.map((s) => (
            <Row key={s.id} session={s} spam={spam[s.id]} ctx={ctx} />
          ))}
        </Group>
      )}
    </div>
  );
}

function Group({
  title,
  guide,
  empty,
  compact,
  children,
}: {
  title: string;
  guide: string;
  empty: string;
  compact?: boolean;
  children: React.ReactNode[];
}) {
  const id = `${guide}-title`;
  return (
    <section aria-labelledby={id} data-guide={guide} className="flex flex-col gap-3">
      <h2 id={id} className="text-ink flex items-baseline gap-2 text-lg font-semibold tracking-tight">
        {title}
        <span className="text-ink-3 text-base font-medium tabular-nums">{children.length}</span>
      </h2>
      {children.length === 0 ? (
        <p className="border-rule-strong text-ink-2 rounded-sm border border-dashed px-4 py-4 text-sm">{empty}</p>
      ) : compact ? (
        <ul className="border-rule bg-paper divide-rule divide-y overflow-hidden rounded-sm border">{children}</ul>
      ) : (
        <ul className="flex flex-col gap-4">{children}</ul>
      )}
    </section>
  );
}

function Facts({ session: s }: { session: Session }) {
  const sec = responseSeconds(s);
  return (
    <dl className="text-ink-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
      <Fact label="Route">{s.rfq ? `${s.rfq.origin} → ${s.rfq.destination}` : "still reading the mail"}</Fact>
      <Fact label="Price">{s.quote ? moneyShort(s.quote.total, s.quote.currency) : "not sent yet"}</Fact>
      <Fact label="Answered in">
        {sec === null ? (
          "not yet"
        ) : (
          <span className={cn("font-semibold", pace(sec) === "on-target" ? "text-ok" : "text-late-text")}>{duration(sec)}</span>
        )}
      </Fact>
    </dl>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt>{label}</dt>
      <dd className="text-ink font-medium tabular-nums">{children}</dd>
    </div>
  );
}

function StatusPill({ session: s, spam, size = "lg" }: { session: Session; spam?: boolean; size?: "lg" | "sm" }) {
  const st = status(s);
  return (
    <span
      data-stage={st.stage}
      data-person={st.person}
      data-spam={spam}
      className={cn(
        "inline-flex w-fit items-center rounded-sm bg-[var(--holder)] font-semibold whitespace-nowrap text-[var(--holder-ink)]",
        size === "lg" ? "px-3 py-1.5 text-base" : "px-2 py-0.5 text-xs",
      )}
    >
      {spam ? "Spam" : st.word}
    </span>
  );
}

// Read → Priced → Quoted → Booked, the current step ringed.
function Progress({ session: s, priced }: { session: Session; priced: boolean }) {
  const n = stepsDone(s, priced);
  return (
    <ol aria-label="Progress" className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-sm sm:gap-x-2">
      {STEPS.map((label, i) => (
        <li key={label} aria-current={i === n ? "step" : undefined} className="flex items-center gap-2">
          {i > 0 && <span aria-hidden className={cn("h-px w-3 sm:w-8", i <= n ? "bg-ok" : "bg-rule-strong")} />}
          <span
            className={cn(
              "inline-flex items-center gap-1.5",
              i < n ? "text-ink" : i === n ? "text-ink font-semibold" : "text-ink-3",
            )}
          >
            <span
              aria-hidden
              className={cn(
                "size-2.5 rounded-full border-2",
                i < n ? "border-ok bg-ok" : i === n ? "border-[var(--st-new)] ring-2 ring-[var(--st-new)]/30" : "border-rule-strong",
              )}
            />
            {label}
            <span className="sr-only">{i < n ? " (done)" : i === n ? (s.paused ? " (next, paused)" : " (current step)") : " (not yet)"}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

// The latest mail each way, two lines at most.
function Previews({ inMail, outMail }: { inMail?: string; outMail?: string }) {
  if (!inMail && !outMail) return null;
  return (
    <dl className="flex flex-col gap-2 text-sm">
      {inMail && (
        <div className="flex flex-col gap-0.5">
          <dt className="caption">Customer wrote</dt>
          <dd className="text-ink-2 line-clamp-2">{inMail}</dd>
        </div>
      )}
      {outMail && (
        <div className="flex flex-col gap-0.5">
          <dt className="caption">We replied</dt>
          <dd className="text-ink-2 line-clamp-2">{outMail}</dd>
        </div>
      )}
    </dl>
  );
}

const bookingLine = (s: Session) => {
  const b = s.booking;
  if (!b) return null;
  const confirmed = b.status ?? (b.confirmation ? "confirmed by the airline" : "waiting for the airline to confirm");
  return [b.booking_reference ?? b.confirmation ?? b.rate_id, shortCarrier(b.airline ?? s.quote?.carrier), confirmed].join(" · ");
};

function Card({ session: s, reason, priced, ctx }: { session: Session; reason?: string; priced: boolean; ctx: Ctx }) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pauseRef = useRef<HTMLButtonElement>(null);
  const { inMail, outMail } = ctx.mails(s.id);
  const booking = bookingLine(s);
  const canPause = !!ctx.apply && !!ctx.applySession;

  const closeConfirm = () => {
    setConfirm(false);
    requestAnimationFrame(() => pauseRef.current?.focus());
  };
  const togglePause = async () => {
    if (!ctx.apply || !ctx.applySession) return;
    setBusy(true);
    setError(null);
    try {
      await setPaused(s, !s.paused, { live: ctx.live, apply: ctx.apply, applySession: ctx.applySession });
      closeConfirm();
    } catch {
      setError(`Could not ${s.paused ? "resume" : "pause"} the agent. Nothing changed; try again or use Show details.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <li
      className={cn(
        "bg-paper border-rule flex flex-col gap-4 rounded-sm border px-4 py-5 sm:px-6",
        s.needs_human && "border-signal border-l-4",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill session={s} />
            {s.paused && (
              <span className="hatch border-rule-strong text-ink inline-flex items-center gap-1 rounded-sm border px-2 py-1 text-sm font-semibold">
                <Pause className="size-3.5" aria-hidden />
                Paused
              </span>
            )}
          </div>
          <p className="text-ink truncate text-lg font-semibold" title={s.customer}>
            {s.customer}
          </p>
        </div>
        <span className="text-ink-3 text-sm tabular-nums">#{s.id}</span>
      </div>
      {s.needs_human && <p className="text-signal-text font-medium">{reason ?? "The agent is not sure how to answer this one."}</p>}
      {s.paused && <p className="text-ink-2 text-sm">The agent sends nothing in this thread until you resume it.</p>}
      <Progress session={s} priced={priced} />
      <Facts session={s} />
      {booking && (
        <p className="text-ink-2 text-sm">
          <span className="caption mr-2">Booking</span>
          <span className="text-ink font-medium">{booking}</span>
        </p>
      )}
      <Previews inMail={inMail} outMail={outMail} />

      {confirm ? (
        <div role="group" aria-label={s.paused ? "Confirm resume" : "Confirm pause"} className="bg-paper-2 border-rule flex flex-col gap-3 rounded-sm border px-4 py-3">
          <p className="text-ink text-sm font-medium">
            {s.paused
              ? `Hand ${s.customer} back to the agent? It may send mails in this thread again.`
              : `Pause the agent for ${s.customer}? It sends nothing in this thread until you resume it.`}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={busy} onClick={togglePause} autoFocus>
              {s.paused ? <Play /> : <Pause />}
              {s.paused ? "Yes, resume" : "Yes, pause"}
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={closeConfirm}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => ctx.onReply(s.id)}>
            <SquarePen />
            Reply myself
          </Button>
          {s.booking && (
            <Button size="sm" variant="outline" onClick={() => ctx.onOpen(s.id, "booking")} className="bg-paper">
              <Package />
              Open booking
            </Button>
          )}
          {s.stage === "tracking" && (
            <Button size="sm" variant="outline" onClick={() => ctx.onOpen(s.id, "thread")} className="bg-paper">
              <MessageCircleQuestion />
              Answer the tracking question
            </Button>
          )}
          {canPause && (
            <Button ref={pauseRef} size="sm" variant="outline" onClick={() => setConfirm(true)} className="bg-paper">
              {s.paused ? <Play /> : <Pause />}
              {s.paused ? "Resume" : "Pause"}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => ctx.onOpen(s.id)}>
            Show details
            <ArrowRight />
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-signal-text text-sm font-medium">
          {error}
        </p>
      )}
    </li>
  );
}

// A compact line that opens in place: the quote, the booking and the last mail each way.
function Row({ session: s, spam, ctx }: { session: Session; spam?: string; ctx: Ctx }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const sec = responseSeconds(s);
  const { inMail, outMail } = ctx.mails(s.id);
  const q = s.quote;
  return (
    <li>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          if (!open) ctx.loadEvents?.(s.id);
          setOpen(!open);
        }}
        className="hover:bg-paper-2 grid w-full grid-cols-[1.25rem_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 px-4 py-3 text-left sm:grid-cols-[1.25rem_minmax(0,1fr)_6rem_5.5rem_3.5rem_14rem]"
      >
        <ChevronDown aria-hidden className={cn("text-ink-3 size-4 transition-transform", open && "rotate-180")} />
        <span className="text-ink truncate font-medium">{s.customer}</span>
        <span className="justify-self-end sm:order-last">
          <StatusPill session={s} spam={!!spam} size="sm" />
        </span>
        <span className="font-condensed text-ink-2 col-start-2 font-semibold sm:col-start-auto">
          {s.rfq ? `${s.rfq.origin} → ${s.rfq.destination}` : "–"}
        </span>
        <span className="text-ink tabular-nums">{q ? moneyShort(q.total, q.currency) : "–"}</span>
        <span
          className={cn(
            "hidden tabular-nums sm:inline",
            sec === null ? "text-ink-3" : pace(sec) === "on-target" ? "text-ok" : "text-late-text",
          )}
        >
          {sec === null ? "–" : duration(sec)}
        </span>
      </button>
      {open && (
        <div id={panelId} className="bg-paper-2 border-rule flex flex-col gap-4 border-t px-4 py-4 sm:pl-12">
          {spam ? (
            <p className="text-ink-2 text-sm">
              <span className="caption mr-2">Ignored as spam</span>
              <span className="text-ink">{spam}</span>
            </p>
          ) : (
            <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
              <div className="flex flex-col gap-0.5">
                <dt className="caption">Quote</dt>
                <dd className="text-ink font-medium">
                  {q
                    ? `${moneyShort(q.total, q.currency)} · ${shortCarrier(q.carrier)} · ${transit(q.transit_days)}${sec === null ? "" : ` · sent in ${duration(sec)}`}`
                    : "No quote sent"}
                </dd>
              </div>
              <div className="flex flex-col gap-0.5">
                <dt className="caption">Booking</dt>
                <dd className="text-ink font-medium">
                  {bookingLine(s) ?? (s.outcome === "lost" || s.outcome === "expired" ? `Not booked (${s.outcome})` : "Not booked yet")}
                </dd>
              </div>
            </dl>
          )}
          <Previews inMail={inMail} outMail={outMail} />
          <div>
            <Button size="sm" variant="outline" onClick={() => ctx.onOpen(s.id)} className="bg-paper">
              Show details
              <ArrowRight />
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}
