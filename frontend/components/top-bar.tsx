import { cn } from "@/lib/utils";
import { duration, usd } from "@/lib/format";

type Props = {
  loading: boolean;
  live: boolean;
  personCount: number;
  personActive: boolean;
  onPersonQueue: () => void;
  tally: { total: number; quoted: number; medianResponse: number | null; llmCost: number } | null;
};

export function TopBar({ loading, live, personCount, personActive, onPersonQueue, tally }: Props) {
  return (
    <header className="bg-console text-console-ink flex h-14 shrink-0 items-stretch gap-3 px-3 sm:gap-6 md:px-5">
      <div className="flex items-center gap-2.5">
        <Mark />
        <p className="flex items-baseline gap-1.5 leading-none">
          <span className="text-[1.0625rem] font-bold tracking-tight">Leylü</span>
          <span className="font-condensed text-console-ink-2 hidden text-[1.0625rem] font-medium sm:inline">Forwarder</span>
        </p>
      </div>

      <nav aria-label="Main" className="hidden items-stretch sm:flex">
        <a
          href="#sessions"
          aria-current="page"
          className="font-condensed relative flex items-center px-1 text-[0.9375rem] font-semibold tracking-wide uppercase after:absolute after:inset-x-0 after:bottom-0 after:h-[3px] after:bg-[var(--st-pricing)]"
        >
          Sessions
        </a>
      </nav>

      {tally && (
        <dl className="text-console-ink-2 ml-auto hidden items-center gap-5 text-sm xl:flex" aria-label="Tonight so far">
          <Tally label="RFQs" value={String(tally.total)} />
          <Tally label="Quoted" value={String(tally.quoted)} />
          <Tally label="Median reply" value={tally.medianResponse === null ? "–" : duration(tally.medianResponse)} />
          <Tally label="LLM cost" value={usd(tally.llmCost)} />
        </dl>
      )}

      <div className={cn("flex items-center gap-2 sm:gap-3", !tally && "ml-auto", tally && "ml-auto xl:ml-0")}>
        <button
          type="button"
          onClick={onPersonQueue}
          aria-pressed={personActive}
          disabled={loading}
          className={cn(
            "flex h-9 items-center gap-2 rounded-sm px-3 text-sm font-semibold",
            personCount > 0
              ? "bg-signal text-signal-ink hover:bg-[oklch(0.5_0.2_27)]"
              : "bg-console-2 text-console-ink-2 hover:text-console-ink",
            personActive && "ring-console-ink ring-2 ring-offset-2 ring-offset-[var(--console)]",
          )}
        >
          <span className="font-condensed text-lg leading-none font-bold tabular-nums">{loading ? "–" : personCount}</span>
          <span className="whitespace-nowrap">
            {personCount === 1 ? "needs a person" : "need a person"}
          </span>
        </button>

        <SourceBadge loading={loading} live={live} />
      </div>
    </header>
  );
}

function Tally({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <dt className="font-condensed text-xs font-semibold tracking-wide uppercase">{label}</dt>
      <dd className="text-console-ink font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function SourceBadge({ loading, live }: { loading: boolean; live: boolean }) {
  const label = loading ? "Connecting" : live ? "Live backend" : "Mock data";
  return (
    <p
      className={cn(
        "font-condensed flex h-9 items-center gap-2 rounded-sm border px-2.5 text-xs font-semibold tracking-wide uppercase",
        live ? "border-[oklch(0.8_0.12_155/0.5)] text-[var(--st-booked)]" : "border-console-2 text-[var(--st-pricing)]",
      )}
      title={live ? "Sessions come from the backend API" : "Backend not reachable: showing bundled sample data"}
    >
      <span className="relative flex size-2">
        {live && <span className="absolute inset-0 animate-ping rounded-full bg-current opacity-60" />}
        <span className="relative size-2 rounded-full bg-current" />
      </span>
      <span className="sr-only sm:not-sr-only">{label}</span>
    </p>
  );
}

// A strip in its holder, cocked: the product's mark.
function Mark() {
  return (
    <svg viewBox="0 0 28 28" className="size-7" aria-hidden>
      <rect x="2" y="5" width="22" height="7" rx="1" fill="var(--st-pricing)" />
      <rect x="6" y="15" width="22" height="7" rx="1" fill="var(--signal)" />
      <rect x="2" y="5" width="6" height="7" fill="oklch(0.27 0.05 80 / 0.25)" />
      <rect x="6" y="15" width="6" height="7" fill="oklch(0.2 0.03 258 / 0.25)" />
    </svg>
  );
}
