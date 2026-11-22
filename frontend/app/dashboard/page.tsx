"use client";

import { useRouter } from "next/navigation";
import { Section } from "@/components/detail/parts";
import { ResponseChart } from "@/components/response-chart";
import { TopBar } from "@/components/top-bar";
import { clock, duration, money, outcomeLabel, usd } from "@/lib/format";
import { useLiveData } from "@/lib/live";
import { COST_CAP_USD, RESPONSE_FULL_S, metrics } from "@/lib/metrics";
import { cn } from "@/lib/utils";
import type { Outcome } from "@/lib/types";

// F4: the CRM dashboard. Chart colours are dataviz reference slots, mapped so a projector reads them right
// (won green, not lost green). This order passes validate_palette.js on the paper surface; the green's low
// surface contrast is covered by the labelled legend and the quotes table. Stage holder colours stay off charts.
const OUTCOME_FILL: Record<Outcome, { fill: string; ink: string }> = {
  won: { fill: "#1baf7a", ink: "#0b0b0b" },
  open: { fill: "#2a78d6", ink: "#ffffff" },
  lost: { fill: "#eb6834", ink: "#ffffff" },
  expired: { fill: "#6250d6", ink: "#ffffff" },
};
const OUTCOME_ORDER: Outcome[] = ["won", "open", "lost", "expired"];

export default function DashboardPage() {
  const router = useRouter();
  const data = useLiveData();
  const m = metrics(data?.sessions ?? []);
  const outcomeTotal = OUTCOME_ORDER.reduce((sum, o) => sum + m.outcomes[o], 0);
  const median = (() => {
    const t = m.quoted.map((s) => m.responseSeconds(s)!).sort((a, b) => a - b);
    return t.length ? t[Math.floor(t.length / 2)] : null;
  })();

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar
        active="dashboard"
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
          <p className="text-ink-2 px-8 py-10">Loading tonight&apos;s numbers…</p>
        ) : (
          <div className="mx-auto flex w-full max-w-[96rem] flex-col gap-8 px-5 pt-6 pb-16 md:px-8">
            <header className="flex flex-col gap-1">
              <h1 className="text-ink text-[1.75rem] leading-tight font-semibold tracking-tight">Tonight so far</h1>
              <p className="text-ink-2 text-sm">Every request since the first RFQ, scored the way 5U scores it. Updates as sessions move.</p>
            </header>

            {/* Hero + KPI row */}
            <div className="border-rule bg-rule grid gap-px overflow-hidden rounded-sm border sm:grid-cols-2 lg:grid-cols-[1.3fr_1fr_1fr_1fr_1fr] [&>*]:bg-paper">
              <Reading label="Average response time">
                <p
                  className={cn(
                    "font-condensed text-[4rem] leading-none font-bold tracking-tight",
                    m.avgResponseS === null ? "text-ink-3" : m.avgResponseS <= RESPONSE_FULL_S ? "text-ok" : "text-late-text",
                  )}
                >
                  {m.avgResponseS !== null ? duration(m.avgResponseS) : "–"}
                </p>
                <Note>RFQ to quote · full points inside 2:00, zero at 6:00</Note>
              </Reading>
              <Reading label="Sessions">
                <Num>{m.sessions}</Num>
                <Note className={m.needsHuman ? "text-signal-text font-semibold" : undefined}>
                  {m.needsHuman ? `${m.needsHuman} need a person` : "nobody waiting"}
                </Note>
              </Reading>
              <Reading label="Quotes sent">
                <Num>{m.quoted.length}</Num>
                <Note>{Math.round(m.quoteRate * 100)}% of sessions</Note>
              </Reading>
              <Reading label="Won">
                <Num>{m.won}</Num>
                <Note>{m.booked.length} booked</Note>
              </Reading>
              <Reading label="LLM cost per won quote">
                <Num>{m.costPerWon !== null ? usd(m.costPerWon) : "–"}</Num>
                <Note>
                  per quote sent {m.costPerQuote !== null ? usd(m.costPerQuote) : "–"} · total {usd(m.totalCost)}
                </Note>
              </Reading>
            </div>

            <div className="grid gap-8 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <Section title="Response time per quote" aside={`${m.quoted.length} quotes, oldest first · amber = over 2:00`}>
                <div className="border-rule bg-paper rounded-sm border px-4 pt-5 pb-3">
                  <ResponseChart quoted={m.quoted} seconds={m.responseSeconds} />
                </div>
              </Section>

              <div className="flex flex-col gap-8">
                <Section title="Against the scoring limits">
                  <div className="border-rule bg-paper flex flex-col gap-4 rounded-sm border px-4 py-4">
                    <Meter label="Quotes inside 2:00" value={`${Math.round(m.within2minRate * 100)}%`} fraction={m.within2minRate} />
                    <Meter label="Sessions quoted" value={`${Math.round(m.quoteRate * 100)}%`} fraction={m.quoteRate} />
                    {/* 5U divides spend by accepted quotes (within 5% of best, first reply, under 6:00), which only the
                        leaderboard knows. Won quotes are the stricter stand-in: never better than the real number. */}
                    <Meter
                      label="Cost per won quote, of the $0.10 line"
                      value={m.costPerWon !== null ? `${((m.costPerWon / COST_CAP_USD) * 100).toFixed(2)}%` : "–"}
                      fraction={(m.costPerWon ?? 0) / COST_CAP_USD}
                    />
                  </div>
                </Section>

                <Section title="Outcomes" aside={`${outcomeTotal} sessions`}>
                  <div className="border-rule bg-paper flex flex-col gap-3 rounded-sm border px-4 py-4">
                    <div className="flex h-7 gap-0.5" role="img" aria-label={OUTCOME_ORDER.map((o) => `${outcomeLabel[o]} ${m.outcomes[o]}`).join(", ")}>
                      {OUTCOME_ORDER.filter((o) => m.outcomes[o] > 0).map((o) => {
                        const share = m.outcomes[o] / outcomeTotal;
                        return (
                          <div
                            key={o}
                            title={`${outcomeLabel[o]}: ${m.outcomes[o]} (${Math.round(share * 100)}%)`}
                            className="flex items-center rounded-[4px] px-1.5 text-xs font-semibold"
                            style={{ width: `${share * 100}%`, background: OUTCOME_FILL[o].fill, color: OUTCOME_FILL[o].ink }}
                          >
                            {share >= 0.15 ? `${Math.round(share * 100)}%` : ""}
                          </div>
                        );
                      })}
                    </div>
                    <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm">
                      {OUTCOME_ORDER.map((o) => (
                        <li key={o} className="text-ink flex items-center gap-1.5">
                          <span className="size-2.5 rounded-[2px]" style={{ background: OUTCOME_FILL[o].fill }} aria-hidden />
                          {outcomeLabel[o]} <span className="text-ink-3 tabular-nums">{m.outcomes[o]}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </Section>
              </div>
            </div>

            <Section title="Quotes" aside={`${m.quoted.length} sent, newest first`}>
              <Table
                head={["Sent", "Session", "Route", "Ask", "Carrier", "All-in", "Response", "LLM", "Outcome"]}
                right={[5, 6, 7]}
                strong={5}
                empty="No quotes yet."
                rows={[...m.quoted].reverse().map((s) => {
                  const sec = m.responseSeconds(s)!;
                  return {
                    key: s.id,
                    href: `/?s=${s.id}`,
                    cells: [
                      clock(s.quote!.sent_at),
                      <SessionCell key="s" id={s.id} name={s.customer} />,
                      s.rfq ? `${s.rfq.origin} → ${s.rfq.destination}` : "–",
                      s.rfq?.ask ?? "–",
                      s.quote!.carrier,
                      money(s.quote!.total, s.quote!.currency),
                      <span key="r" className={cn("font-semibold", sec <= RESPONSE_FULL_S ? "text-ok" : "text-late-text")}>{duration(sec)}</span>,
                      usd(s.llm_cost_usd),
                      outcomeLabel[s.outcome],
                    ],
                  };
                })}
              />
            </Section>

            <Section title="Booked shipments" aside={`${m.booked.length} booked`}>
              <Table
                head={["Booking", "Session", "Route", "Rate", "All-in", "Latest status"]}
                right={[4]}
                strong={4}
                empty="Nothing booked yet. When a customer accepts, the agent books the quoted rate and it lands here."
                rows={m.booked.map((s) => {
                  const last = s.status_updates.at(-1);
                  return {
                    key: s.id,
                    href: `/?s=${s.id}`,
                    cells: [
                      <span key="b" className="font-mono text-[0.8125rem]">{s.booking!.booking_reference ?? s.booking!.confirmation ?? "–"}</span>,
                      <SessionCell key="s" id={s.id} name={s.customer} />,
                      s.rfq ? `${s.rfq.origin} → ${s.rfq.destination}` : "–",
                      <span key="r" className="font-mono text-[0.8125rem]">{s.booking!.rate_id}</span>,
                      s.quote ? money(s.quote.total, s.quote.currency) : "–",
                      last ? `${clock(last.at)} · ${last.text}` : (s.booking!.status ?? "–"),
                    ],
                  };
                })}
              />
            </Section>
          </div>
        )}
      </main>
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

function Num({ children }: { children: React.ReactNode }) {
  return <p className="font-condensed text-ink text-[2.5rem] leading-none font-bold tracking-tight">{children}</p>;
}

function Note({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("text-ink-2 text-sm", className)}>{children}</p>;
}

// Same-ramp track with an ink fill; the figure sits beside the bar in text ink.
function Meter({ label, value, fraction }: { label: string; value: string; fraction: number }) {
  const f = Math.min(1, Math.max(0, fraction));
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-ink text-[0.9375rem]">{label}</span>
        <span className="text-ink font-semibold tabular-nums">{value}</span>
      </div>
      <div className="bg-paper-2 border-rule relative h-2.5 rounded-[2px] border" aria-hidden>
        <div className="absolute inset-y-0 left-0 rounded-[1px] bg-[#2a78d6]" style={{ width: `${f * 100}%`, minWidth: f > 0 ? 3 : 0 }} />
      </div>
    </div>
  );
}

function SessionCell({ id, name }: { id: number; name: string }) {
  return (
    <span className="flex items-baseline gap-2">
      <span className="font-condensed text-ink-3 font-bold tabular-nums">{id}</span>
      <span className="text-ink font-medium">{name}</span>
    </span>
  );
}

type Row = { key: number; href: string; cells: React.ReactNode[] };

// A strip-board table: hairline rows on paper; a row opens its session.
function Table({ head, rows, right, strong, empty }: { head: string[]; rows: Row[]; right: number[]; strong?: number; empty: string }) {
  const router = useRouter();
  if (!rows.length) {
    return (
      <div className="border-rule-strong flex rounded-sm border border-dashed px-4 py-4">
        <p className="text-ink-2 text-sm">{empty}</p>
      </div>
    );
  }
  return (
    <div className="border-rule bg-paper thin-scroll overflow-x-auto rounded-sm border">
      <table className="w-full min-w-[44rem] text-sm tabular-nums">
        <thead>
          <tr className="border-rule border-b">
            {head.map((h, i) => (
              <th key={h} className={cn("caption px-3 py-2.5 text-left", right.includes(i) && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.key}
              onClick={() => router.push(r.href)}
              className="border-rule hover:bg-paper-2 cursor-pointer border-b last:border-b-0"
              title="Open this session"
            >
              {r.cells.map((c, i) => (
                <td key={i} className={cn("text-ink-2 px-3 py-2", right.includes(i) && "text-right", i === strong && "text-ink font-semibold")}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
