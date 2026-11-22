"use client";
// The calm view for a first-time user: what needs a person, what is being answered, what is done.
// Internals (event log, bids, gate wording) stay in the detailed view behind "Show details".
import { ArrowRight, SquarePen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { duration, moneyShort, pace, responseSeconds } from "@/lib/format";
import type { Session } from "@/lib/types";

type Props = {
  sessions: Session[]; // newest first, spam already left out
  loading: boolean;
  reasons: Record<number, string>;
  onOpen: (id: number) => void;
  onReply: (id: number) => void;
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

export function SimpleView({ sessions, loading, reasons, onOpen, onReply }: Props) {
  if (loading) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-5 pt-8" aria-hidden>
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="bg-paper h-24 animate-pulse rounded-sm" />
        ))}
      </div>
    );
  }
  const needs = sessions.filter((s) => s.needs_human);
  const working = sessions.filter((s) => !s.needs_human && (s.stage === "new" || s.stage === "pricing"));
  // "Today" = the 24 hours up to the newest request (the mock night is not today's date).
  const newest = sessions.length ? Date.parse(sessions[0].received_at) : 0;
  const done = sessions.filter(
    (s) => !s.needs_human && s.stage !== "new" && s.stage !== "pricing" && newest - Date.parse(s.received_at) < DAY_MS,
  );

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-10 px-5 pt-8 pb-16 md:px-8">
      <header className="flex flex-col gap-1.5">
        <h1 className="text-ink text-[1.75rem] leading-tight font-semibold tracking-tight">
          {needs.length === 0
            ? "Nothing needs you right now"
            : needs.length === 1
              ? "One request needs you"
              : `${needs.length} requests need you`}
        </h1>
        <p className="text-ink-2 max-w-2xl">
          The agent answers every air-freight request on its own. It only asks you when it can&apos;t be sure. Open a request with
          &ldquo;Show details&rdquo; to see everything it did.
        </p>
      </header>

      <Group title="Needs you" guide="simple-needs" empty="All clear. Requests the agent can't answer alone show up here.">
        {needs.map((s) => (
          <Card key={s.id} session={s} reason={reasons[s.id]} onOpen={onOpen} onReply={onReply} />
        ))}
      </Group>

      <Group title="Being answered" guide="simple-working" empty="No request is being priced right now.">
        {working.map((s) => (
          <Card key={s.id} session={s} onOpen={onOpen} onReply={onReply} />
        ))}
      </Group>

      <Group title="Done" guide="simple-done" empty="Nothing answered yet today." compact>
        {done.map((s) => (
          <Row key={s.id} session={s} onOpen={onOpen} />
        ))}
      </Group>
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
        <ul className="flex flex-col gap-3">{children}</ul>
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

function StatusPill({ session: s, size = "lg" }: { session: Session; size?: "lg" | "sm" }) {
  const st = status(s);
  return (
    <span
      data-stage={st.stage}
      data-person={st.person}
      className={cn(
        "inline-flex w-fit items-center rounded-sm bg-[var(--holder)] font-semibold text-[var(--holder-ink)]",
        size === "lg" ? "px-3 py-1.5 text-base" : "px-2 py-0.5 text-xs",
      )}
    >
      {st.word}
    </span>
  );
}

function Card({
  session: s,
  reason,
  onOpen,
  onReply,
}: {
  session: Session;
  reason?: string;
  onOpen: (id: number) => void;
  onReply: (id: number) => void;
}) {
  return (
    <li
      className={cn(
        "bg-paper border-rule flex flex-col gap-3 rounded-sm border px-4 py-4 sm:px-5",
        s.needs_human && "border-signal border-l-4",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-2">
          <StatusPill session={s} />
          <p className="text-ink truncate text-lg font-semibold" title={s.customer}>
            {s.customer}
          </p>
        </div>
        <span className="text-ink-3 text-sm tabular-nums">#{s.id}</span>
      </div>
      {s.needs_human && <p className="text-signal-text font-medium">{reason ?? "The agent is not sure how to answer this one."}</p>}
      <Facts session={s} />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => onOpen(s.id)} className="bg-paper">
          Show details
          <ArrowRight />
        </Button>
        <Button size="sm" onClick={() => onReply(s.id)}>
          <SquarePen />
          Reply myself
        </Button>
      </div>
    </li>
  );
}

function Row({ session: s, onOpen }: { session: Session; onOpen: (id: number) => void }) {
  const sec = responseSeconds(s);
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(s.id)}
        className="hover:bg-paper-2 grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3 text-left sm:grid-cols-[minmax(0,1.4fr)_6rem_6rem_4rem_auto]"
        aria-label={`Show details for ${s.customer}`}
      >
        <span className="text-ink truncate font-medium">{s.customer}</span>
        <span className="sm:order-last">
          <StatusPill session={s} size="sm" />
        </span>
        <span className="font-condensed text-ink-2 font-semibold">{s.rfq ? `${s.rfq.origin} → ${s.rfq.destination}` : "–"}</span>
        <span className="text-ink tabular-nums">{s.quote ? moneyShort(s.quote.total, s.quote.currency) : "–"}</span>
        <span className={cn("tabular-nums", sec === null ? "text-ink-3" : pace(sec) === "on-target" ? "text-ok" : "text-late-text")}>
          {sec === null ? "–" : duration(sec)}
        </span>
      </button>
    </li>
  );
}
