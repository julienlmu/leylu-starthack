import { Ban, CirclePause, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  COST_ZERO_USD,
  airOptions,
  TARGET_SECONDS,
  TRACK,
  ZERO_SECONDS,
  clock,
  duration,
  money,
  outcomeLabel,
  pace,
  responseSeconds,
  sameOption,
  stageLabel,
  transit,
  usd,
} from "@/lib/format";
import type { Event, Session } from "@/lib/types";

export function SessionHead({ session: s, events, spam }: { session: Session; events: Event[]; spam?: string }) {
  const reason = [...events].reverse().find((e) => e.kind === "needs_human")?.text;
  return (
    <header className="flex flex-col gap-4" data-guide="head">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <p
          data-stage={s.stage}
          data-person={s.needs_human}
          data-spam={spam !== undefined || undefined}
          className={cn(
            "font-condensed flex h-16 min-w-16 items-center justify-center rounded-sm bg-[var(--holder)] px-3 text-[2.75rem] leading-none font-bold text-[var(--holder-ink)] tabular-nums",
            s.paused && "hatch",
          )}
          aria-label={`Session ${s.id}`}
        >
          {s.id}
        </p>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <h1 className="text-ink text-[1.75rem] leading-tight font-semibold tracking-tight text-balance">{s.customer}</h1>
          <p className="text-ink-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
            <span>
              RFQ in at <span className="text-ink font-medium tabular-nums">{clock(s.received_at)}</span>
            </span>
            <span>
              Thread <span className="text-ink font-mono text-[0.8125rem]">{s.thread_id}</span>
            </span>
            <span>
              Outcome <OutcomeWord outcome={s.outcome} />
            </span>
          </p>
        </div>
      </div>

      <StageTrack session={s} />

      {spam !== undefined && (
        <div role="status" className="bg-paper border-rule-strong text-ink flex flex-wrap items-start gap-x-4 gap-y-2 rounded-sm border px-4 py-3">
          <p className="flex items-center gap-2 font-semibold">
            <Ban className="size-5" aria-hidden />
            Spam
          </p>
          <p className="min-w-0 flex-1 text-[0.9375rem]">
            {spam}
            <span className="text-ink-2 mt-0.5 block text-sm">The agent sent no reply, asked no carrier and made no LLM call.</span>
          </p>
        </div>
      )}

      {(s.needs_human || s.paused) && (
        <div
          role="status"
          className={cn(
            "flex flex-wrap items-start gap-x-4 gap-y-2 rounded-sm px-4 py-3",
            s.needs_human ? "bg-signal text-signal-ink" : "bg-paper-2 text-ink border-rule-strong border",
          )}
        >
          <p className="flex items-center gap-2 font-semibold">
            {s.needs_human ? <TriangleAlert className="size-5" aria-hidden /> : <CirclePause className="size-5" aria-hidden />}
            {s.needs_human ? "Needs a person" : "Paused"}
          </p>
          <p className="min-w-0 flex-1 text-[0.9375rem]">
            {s.needs_human ? (reason ?? "The agent flagged this session for a person.") : "A person has taken over this session."}
            {s.paused && (
              <span className={cn("mt-0.5 block text-sm", s.needs_human ? "text-signal-ink/85" : "text-ink-2")}>
                Paused: the agent sends nothing in this thread until a person resumes it.
              </span>
            )}
          </p>
        </div>
      )}
    </header>
  );
}

function OutcomeWord({ outcome }: { outcome: Session["outcome"] }) {
  return (
    <span
      className={cn(
        "font-semibold",
        outcome === "won" && "text-ok",
        (outcome === "lost" || outcome === "expired") && "text-ink-2",
        outcome === "open" && "text-ink",
      )}
    >
      {outcomeLabel[outcome]}
    </span>
  );
}

// The path a session walks, as a row of strip boxes. Passed boxes keep a sliver of their holder colour.
function StageTrack({ session: s }: { session: Session }) {
  const failed = s.stage === "failed";
  const current = failed ? -1 : TRACK.indexOf(s.stage);
  const steps = failed ? [...TRACK.slice(0, 2), "failed" as const] : TRACK;
  return (
    <ol className="border-rule bg-rule flex gap-px overflow-hidden rounded-sm border" aria-label="Stage">
      {steps.map((st, i) => {
        const isCurrent = failed ? st === "failed" : i === current;
        const passed = failed ? st !== "failed" : i < current;
        return (
          <li
            key={st}
            data-stage={st}
            aria-current={isCurrent ? "step" : undefined}
            className={cn(
              "font-condensed relative flex h-9 min-w-0 flex-1 items-center justify-center gap-1.5 px-1 text-[0.6875rem] font-semibold uppercase @2xl:text-[0.8125rem] @2xl:tracking-wide",
              isCurrent && "bg-[var(--holder)] text-[var(--holder-ink)]",
              passed && "bg-paper text-ink-2",
              !isCurrent && !passed && "bg-paper text-ink-3",
            )}
          >
            {passed && <span className="size-2.5 shrink-0 rounded-[2px] bg-[var(--holder)]" aria-hidden />}
            <span className="min-w-0">{stageLabel[st]}</span>
          </li>
        );
      })}
    </ol>
  );
}

// The three numbers each quote is scored on, at the scale they are scored on.
export function Scoreboard({ session: s }: { session: Session }) {
  const sec = responseSeconds(s);
  const air = airOptions(s.bids);
  const lowest = air.length ? Math.min(...air.map((b) => b.total)) : null;
  const delta = s.quote && lowest ? (s.quote.total - lowest) / lowest : null;
  const quotedIsLowest = s.quote ? air.some((b) => sameOption(b, s.quote!) && b.total === lowest) : false;

  return (
    <div className="border-rule bg-rule grid gap-px overflow-hidden rounded-sm border @2xl:grid-cols-3 [&>*]:bg-paper" data-guide="scoreboard">
      <Reading label="Response time">
        {sec === null ? (
          <Absent>{s.stage === "failed" ? "Never quoted" : "No quote sent yet"}</Absent>
        ) : (
          <Big tone={pace(sec) === "on-target" ? "ok" : "late"}>{duration(sec)}</Big>
        )}
        <Note>
          {sec === null
            ? s.stage === "failed"
              ? "Zero points for this request"
              : "Full points if it goes out within 2:00"
            : pace(sec) === "on-target"
              ? `Inside the ${duration(TARGET_SECONDS)} target: full points`
              : pace(sec) === "late"
                ? `${duration(sec - TARGET_SECONDS)} over target: partial points`
                : "Past 6:00: zero points"}
        </Note>
        <TimeScale sec={sec} />
      </Reading>

      <Reading label="All-in price quoted">
        {s.quote ? <Big tone="ink">{money(s.quote.total, s.quote.currency)}</Big> : <Absent>No price yet</Absent>}
        <Note>
          {s.quote ? (
            <>
              {s.quote.carrier} · {transit(s.quote.transit_days)}
              {s.rfq && <> · {s.rfq.ask} asked</>}
            </>
          ) : air.length ? (
            `${air.length} prices collected, none sent`
          ) : (
            "Sheet, portal and carrier bids pending"
          )}
        </Note>
        {s.quote && delta !== null && (
          <p className="text-ink-2 mt-auto pt-2 text-sm">
            {quotedIsLowest || delta === 0 ? (
              <span className="text-ok font-semibold">Lowest of {air.length} options</span>
            ) : (
              <>
                <span className="text-ink font-semibold tabular-nums">+{(delta * 100).toFixed(1)}%</span> over the lowest of {air.length}{" "}
                options
              </>
            )}
          </p>
        )}
      </Reading>

      <Reading label="LLM cost">
        <Big tone={s.llm_cost_usd >= COST_ZERO_USD ? "late" : "ink"}>{usd(s.llm_cost_usd)}</Big>
        <Note>
          {((s.llm_cost_usd / COST_ZERO_USD) * 100).toFixed(2)}% of the $0.10 zero-points line
        </Note>
        <CostScale usd={s.llm_cost_usd} />
      </Reading>
    </div>
  );
}

function Reading({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 px-4 pt-3 pb-4">
      <p className="caption">{label}</p>
      {children}
    </div>
  );
}

function Big({ children, tone }: { children: React.ReactNode; tone: "ok" | "late" | "ink" | "muted" }) {
  return (
    <p
      className={cn(
        "font-condensed text-[2.5rem] leading-none font-bold tracking-tight tabular-nums",
        tone === "ok" && "text-ok",
        tone === "late" && "text-late-text",
        tone === "ink" && "text-ink",
        tone === "muted" && "text-ink-3",
      )}
    >
      {children}
    </p>
  );
}

// What a reading shows before it exists: caption scale, so display size only carries real numbers.
function Absent({ children }: { children: React.ReactNode }) {
  return <p className="text-ink-3 flex h-10 items-end text-xl leading-none font-semibold">{children}</p>;
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="text-ink-2 truncate text-sm">{children}</p>;
}

// 0:00 → 6:00. Full points up to 2:00, falling to zero at 6:00.
function TimeScale({ sec }: { sec: number | null }) {
  const pct = (v: number) => `${(Math.min(v, ZERO_SECONDS) / ZERO_SECONDS) * 100}%`;
  return (
    <div className="mt-auto pt-3" aria-hidden>
      <div className="bg-paper-2 border-rule relative h-2.5 overflow-visible rounded-[2px] border">
        <div className="absolute inset-y-0 left-0 bg-[oklch(0.8_0.12_155/0.45)]" style={{ width: pct(TARGET_SECONDS) }} />
        <div
          className="absolute inset-y-0 bg-gradient-to-r from-[oklch(0.87_0.135_92/0.6)] to-[oklch(0.56_0.205_27/0.35)]"
          style={{ left: pct(TARGET_SECONDS), right: 0 }}
        />
        {sec !== null && (
          <div
            className={cn("absolute -top-1.5 -bottom-1.5 w-[3px] -translate-x-1/2 rounded-full", pace(sec) === "on-target" ? "bg-ok" : "bg-late-text")}
            style={{ left: pct(sec) }}
          />
        )}
      </div>
      <div className="caption relative mt-1.5 h-3">
        <span className="absolute left-0">0:00</span>
        <span className="absolute -translate-x-1/2" style={{ left: pct(TARGET_SECONDS) }}>
          2:00 target
        </span>
        <span className="absolute right-0">6:00</span>
      </div>
    </div>
  );
}

function CostScale({ usd: v }: { usd: number }) {
  const pct = Math.min(1, v / COST_ZERO_USD) * 100;
  return (
    <div className="mt-auto pt-3" aria-hidden>
      <div className="bg-paper-2 border-rule relative h-2.5 rounded-[2px] border">
        <div className="bg-ink absolute inset-y-0 left-0 min-w-[3px] rounded-[1px]" style={{ width: `${pct}%` }} />
      </div>
      <div className="caption mt-1.5 flex justify-between">
        <span>$0</span>
        <span>$0.10</span>
      </div>
    </div>
  );
}
