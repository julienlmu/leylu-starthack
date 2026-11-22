"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Section } from "@/components/detail/parts";
import { TopBar } from "@/components/top-bar";
import { clock } from "@/lib/format";
import { useLiveData } from "@/lib/live";
import { metrics } from "@/lib/metrics";
import { PARTS, WEIGHTS, scoreboard, type Leak, type Part, type RoundScore } from "@/lib/score";
import { cn } from "@/lib/utils";

// Scoreboard: where every (estimated) point came from, round by round. Same dataviz slots as the Dashboard.
const PART_FILL: Record<Part, string> = { accuracy: "#2a78d6", time: "#eb6834", cost: "#1baf7a", tracking: "#6250d6" };
const PART_LABEL: Record<Part, string> = { accuracy: "Accuracy", time: "Speed", cost: "LLM cost", tracking: "Tracking" };
const LEAK_LABEL: Record<Leak, string> = {
  unquoted: "Request never quoted",
  lost: "Quote lost or expired",
  late: "Reply slower than 2:00",
  cost: "LLM spend per quote",
};
const SHOWN_ROUNDS = 24;

const pts = (n: number) => n.toFixed(1);

export default function ScoreboardPage() {
  const router = useRouter();
  const data = useLiveData();
  const sessions = data?.sessions ?? [];
  const m = metrics(sessions);
  const sb = scoreboard(sessions);
  const median = (() => {
    const t = m.quoted.map((s) => m.responseSeconds(s)!).sort((a, b) => a - b);
    return t.length ? t[Math.floor(t.length / 2)] : null;
  })();
  const shown = sb.rounds.slice(-SHOWN_ROUNDS);
  const leakTotal = Object.values(sb.leaks).reduce((a, b) => a + b, 0);
  const biggestLeak = (Object.entries(sb.leaks) as [Leak, number][]).sort((a, b) => b[1] - a[1])[0];

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar
        active="scoreboard"
        loading={!data}
        live={data?.live ?? false}
        connected={data?.connected ?? false}
        personCount={m.needsHuman}
        personActive={false}
        onPersonQueue={() => router.push("/")}
        tally={data ? { total: m.sessions, quoted: m.quoted.length, medianResponse: median, llmCost: m.totalCost } : null}
      />

      <main className="bg-paper-2 flex-1">
        {!data ? (
          <p className="text-ink-2 px-8 py-10">Adding up the rounds…</p>
        ) : (
          <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-8 px-5 pt-6 pb-16 md:px-8">
            <header className="flex flex-col gap-1">
              <h1 className="text-ink text-[1.75rem] leading-tight font-semibold tracking-tight">Round scoreboard</h1>
              <p className="text-ink-2 text-sm">
                Where every point came from, one 6-minute round at a time. Estimated from our own sessions with the board&apos;s
                weights (accuracy {WEIGHTS.accuracy}, cost {WEIGHTS.cost}, time {WEIGHTS.time}, tracking {WEIGHTS.tracking}); 5U&apos;s
                board has the final verdicts.
              </p>
            </header>

            <div className="border-rule bg-rule grid gap-px overflow-hidden rounded-sm border sm:grid-cols-2 lg:grid-cols-4 [&>*]:bg-paper">
              <Reading label="Estimated points">
                <Big>{pts(sb.total)}</Big>
                <Note>
                  {sb.max ? `${Math.round((sb.total / sb.max) * 100)}% of the ${Math.round(sb.max)} on the table` : "no requests yet"}
                </Note>
              </Reading>
              <Reading label="Last round">
                <Big>{sb.last ? pts(sb.last.total) : "–"}</Big>
                <Note className={sb.last && sb.prev ? (sb.last.total >= sb.prev.total ? "text-ok font-semibold" : "text-late-text font-semibold") : undefined}>
                  {sb.last ? `R${shortRound(sb.last)} · ${clock(sb.last.start)}` : "–"}
                  {sb.last && sb.prev ? ` · ${sb.last.total >= sb.prev.total ? "▲" : "▼"} ${pts(Math.abs(sb.last.total - sb.prev.total))} vs previous` : ""}
                </Note>
              </Reading>
              <Reading label="Average per round">
                <Big>{sb.avg !== null ? pts(sb.avg) : "–"}</Big>
                <Note>{sb.rounds.length} rounds with mail</Note>
              </Reading>
              <Reading label="Best round">
                <Big>{sb.best ? pts(sb.best.total) : "–"}</Big>
                <Note>{sb.best ? `R${shortRound(sb.best)} · ${clock(sb.best.start)}` : "–"}</Note>
              </Reading>
            </div>

            <div className="grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <Section title="Points per round, by part" aside={`last ${shown.length} rounds, oldest first`}>
                <div className="border-rule bg-paper flex flex-col gap-3 rounded-sm border px-4 pt-4 pb-3">
                  <Legend />
                  <RoundChart rounds={shown} />
                </div>
              </Section>

              <div className="flex flex-col gap-8">
                <Section title="Where we lose points" aside={leakTotal ? `${pts(leakTotal)} pts` : undefined}>
                  <div className="border-rule bg-paper flex flex-col gap-4 rounded-sm border px-4 py-4">
                    {(Object.keys(LEAK_LABEL) as Leak[]).map((k) => (
                      <LeakBar key={k} label={LEAK_LABEL[k]} value={sb.leaks[k]} fraction={leakTotal ? sb.leaks[k] / leakTotal : 0} />
                    ))}
                  </div>
                </Section>
                {biggestLeak && biggestLeak[1] > 0 && (
                  <div className="bg-console text-console-ink rounded-sm px-4 py-4 text-sm">
                    <p className="font-condensed mb-1 text-xs font-semibold tracking-wide text-[var(--st-pricing)] uppercase">Biggest lever</p>
                    <p>
                      {LEAK_LABEL[biggestLeak[0]]} costs us {pts(biggestLeak[1])} pts so far,{" "}
                      {Math.round((biggestLeak[1] / leakTotal) * 100)}% of everything we leave on the table.
                    </p>
                  </div>
                )}
              </div>
            </div>

            <Section title="Rounds" aside={`${sb.rounds.length} rounds, newest first`}>
              <RoundTable rounds={[...sb.rounds].reverse()} />
            </Section>
          </div>
        )}
      </main>
    </div>
  );
}

// Rounds are numbered from the first mail we saw, so R1 is our first round of the night.
const shortRound = (r: RoundScore) => String(r.n);

function Reading({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 px-4 pt-3 pb-4">
      <p className="caption">{label}</p>
      {children}
    </div>
  );
}

function Big({ children }: { children: React.ReactNode }) {
  return <p className="font-condensed text-ink text-[2.5rem] leading-none font-bold tracking-tight tabular-nums">{children}</p>;
}

function Note({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("text-ink-2 text-sm", className)}>{children}</p>;
}

function Legend() {
  return (
    <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
      {PARTS.map((p) => (
        <li key={p} className="text-ink flex items-center gap-1.5">
          <span className="size-2.5 rounded-[2px]" style={{ background: PART_FILL[p] }} aria-hidden />
          {PART_LABEL[p]} <span className="text-ink-3">/{WEIGHTS[p]}</span>
        </li>
      ))}
    </ul>
  );
}

// Stacked columns, one per round. Scale = the tallest round, so a quiet night still fills the chart.
function RoundChart({ rounds }: { rounds: RoundScore[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!rounds.length) return <p className="text-ink-2 text-sm">No rounds yet.</p>;
  const top = Math.max(...rounds.map((r) => r.total), 1);
  return (
    <div className="flex flex-col gap-1">
      <div className="relative flex h-56 items-end gap-1">
        <div className="bg-rule-strong absolute inset-x-0 bottom-0 h-px" />
        {rounds.map((r, i) => (
          <button
            key={r.round}
            type="button"
            aria-label={`Round ${shortRound(r)}: ${pts(r.total)} points`}
            onPointerEnter={() => setHover(i)}
            onPointerLeave={() => setHover(null)}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
            className="relative flex h-full min-w-0 flex-1 flex-col-reverse items-center outline-none"
          >
            {PARTS.map((p) => (
              <span
                key={p}
                className={cn("block w-full max-w-9 transition-opacity", hover !== null && hover !== i && "opacity-50")}
                style={{ height: `${(r.points[p] / top) * 100}%`, background: PART_FILL[p] }}
              />
            ))}
            {hover === i && (
              <span
                className="border-rule bg-paper pointer-events-none absolute z-10 rounded-sm border px-2 py-1.5 text-left whitespace-nowrap shadow-sm"
                style={{ bottom: `calc(${(r.total / top) * 100}% + 6px)` }}
              >
                <span className="font-condensed text-ink block text-lg leading-tight font-bold">
                  R{shortRound(r)} · {pts(r.total)} pts
                </span>
                {PARTS.map((p) => (
                  <span key={p} className="text-ink-2 flex justify-between gap-4 text-xs tabular-nums">
                    <span>{PART_LABEL[p]}</span>
                    <span>{pts(r.points[p])}</span>
                  </span>
                ))}
              </span>
            )}
          </button>
        ))}
      </div>
      <div className="flex gap-1">
        {rounds.map((r) => (
          <span key={r.round} className="text-ink-3 min-w-0 flex-1 text-center font-mono text-[10px] tabular-nums">
            {shortRound(r)}
          </span>
        ))}
      </div>
    </div>
  );
}

function LeakBar({ label, value, fraction }: { label: string; value: number; fraction: number }) {
  const f = Math.min(1, Math.max(0, fraction));
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-ink text-[0.9375rem]">{label}</span>
        <span className="text-ink font-semibold tabular-nums">{pts(value)}</span>
      </div>
      <div className="bg-paper-2 border-rule relative h-2.5 rounded-[2px] border" aria-hidden>
        <div className="bg-late absolute inset-y-0 left-0 rounded-[1px]" style={{ width: `${f * 100}%`, minWidth: f > 0 ? 3 : 0 }} />
      </div>
    </div>
  );
}

function RoundTable({ rounds }: { rounds: RoundScore[] }) {
  const router = useRouter();
  if (!rounds.length) {
    return (
      <div className="border-rule-strong flex rounded-sm border border-dashed px-4 py-4">
        <p className="text-ink-2 text-sm">No rounds yet. The first mail starts round one.</p>
      </div>
    );
  }
  const head = ["Round", "Started", "Requests", "Outcome", ...PARTS.map((p) => PART_LABEL[p]), "Total"];
  return (
    <div className="border-rule bg-paper thin-scroll overflow-x-auto rounded-sm border">
      <table className="w-full min-w-[52rem] text-sm tabular-nums">
        <thead>
          <tr className="border-rule border-b">
            {head.map((h, i) => (
              <th key={h} className={cn("caption px-3 py-2.5 text-left", i >= 4 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rounds.map((r) => {
            const first = r.sessions[0].session;
            return (
              <tr
                key={r.round}
                onClick={() => router.push(`/?s=${first.id}`)}
                className="border-rule hover:bg-paper-2 cursor-pointer border-b last:border-b-0"
                title="Open this round's session"
              >
                <td className="font-condensed text-ink px-3 py-2 font-bold">R{shortRound(r)}</td>
                <td className="text-ink-2 px-3 py-2">{clock(r.start)}</td>
                <td className="text-ink-2 px-3 py-2">
                  {r.sessions.map((x) => (
                    <span key={x.session.id} className="mr-2 inline-flex items-baseline gap-1.5">
                      <span className="font-condensed text-ink-3 font-bold">{x.session.id}</span>
                      <span className="text-ink">{x.session.customer}</span>
                    </span>
                  ))}
                </td>
                <td className="px-3 py-2">
                  {r.sessions.map((x) => (
                    <OutcomePill key={x.session.id} quoted={!!x.session.quote} outcome={x.session.outcome} human={x.session.needs_human} />
                  ))}
                </td>
                {PARTS.map((p) => (
                  <td key={p} className="text-ink-2 px-3 py-2 text-right">
                    {pts(r.points[p])}
                  </td>
                ))}
                <td className="text-ink px-3 py-2 text-right font-semibold">{pts(r.total)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function OutcomePill({ quoted, outcome, human }: { quoted: boolean; outcome: string; human: boolean }) {
  const [label, cls] = human
    ? ["Needs a person", "bg-signal-wash text-signal-text"]
    : !quoted
      ? ["Not quoted", "bg-paper-2 text-ink-2"]
      : outcome === "won"
        ? ["Won", "bg-[oklch(0.32_0.07_155)] text-[oklch(0.86_0.12_155)]"]
        : outcome === "open"
          ? ["Quoted", "bg-[oklch(0.32_0.06_300)] text-[oklch(0.86_0.08_300)]"]
          : ["Lost", "bg-[oklch(0.32_0.06_60)] text-late-text"];
  return <span className={cn("mr-1 inline-block rounded-sm px-1.5 py-0.5 text-xs font-semibold whitespace-nowrap", cls)}>{label}</span>;
}
