import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Empty } from "./parts";
import { money, sameOption, sourceLabel } from "@/lib/format";
import type { Session } from "@/lib/types";

// Every price the agent collected, the quoted one marked, then how the quoted all-in adds up.
export function PriceOptions({ session: s }: { session: Session }) {
  const options = [...s.bids];
  if (s.quote && !options.some((o) => sameOption(o, s.quote!))) options.push(s.quote);
  if (!options.length) {
    return (
      <Empty title="No prices yet">
        Rate sheet, portal and carrier bids land here as the agent collects them; the quoted one is marked.
      </Empty>
    );
  }
  const sorted = options.sort((a, b) => a.total - b.total);
  const lowest = sorted[0].total;
  const fastest = Math.min(...sorted.map((o) => o.transit_days));

  return (
    <div className="flex flex-col gap-5">
      <div className="border-rule overflow-x-auto rounded-sm border">
        <table className="w-full min-w-[24rem] border-collapse text-sm [&_td]:whitespace-nowrap [&_thead_th]:whitespace-nowrap">
          <caption className="sr-only">Price options, lowest first</caption>
          <thead>
            <tr className="bg-paper-2 border-rule border-b">
              <th scope="col" className="caption px-3 py-2 text-left">Carrier</th>
              <th scope="col" className="caption px-3 py-2 text-right">Transit</th>
              <th scope="col" className="caption px-3 py-2 text-right">All-in</th>
              <th scope="col" className="caption px-3 py-2 text-right">Over lowest</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((o, i) => {
              const quoted = s.quote ? sameOption(o, s.quote) : false;
              const d = (o.total - lowest) / lowest;
              return (
                <tr
                  key={`${o.carrier}-${o.source}-${i}`}
                  className={cn("border-rule border-b last:border-b-0", quoted ? "bg-[oklch(0.95_0.03_300)]" : "bg-paper")}
                >
                  <th scope="row" className="px-3 py-2.5 text-left font-medium">
                    <span className="flex items-center gap-2">
                      {quoted && (
                        <span className="font-condensed bg-[var(--st-quoted)] text-[var(--st-quoted-ink)] flex items-center gap-1 rounded-[2px] px-1.5 py-0.5 text-[0.6875rem] font-bold tracking-[0.06em] uppercase">
                          <Check className="size-3" aria-hidden />
                          Quoted
                        </span>
                      )}
                      <span className={cn(quoted && "font-semibold")}>{o.carrier}</span>
                    </span>
                    <span className="text-ink-2 mt-0.5 block text-xs font-normal">
                      {sourceLabel[o.source]}
                      {o.rate_id && <span className="text-ink-3 font-mono"> · {o.rate_id}</span>}
                    </span>
                  </th>
                  <td className={cn("px-3 py-2.5 text-right tabular-nums", o.transit_days === fastest ? "text-ink font-semibold" : "text-ink-2")}>
                    {o.transit_days} {o.transit_days === 1 ? "day" : "days"}
                  </td>
                  <td className={cn("px-3 py-2.5 text-right tabular-nums", quoted ? "font-bold" : "font-medium")}>{money(o.total, o.currency)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {d === 0 ? <span className="text-ok font-semibold">lowest</span> : <span className="text-ink-2">+{(d * 100).toFixed(1)}%</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {s.quote && (s.quote.breakdown?.length ?? 0) > 0 && (
        <div>
          <h3 className="text-ink mb-2 text-sm font-semibold">
            Quote breakdown <span className="text-ink-3 font-normal">· {s.quote.chargeable_weight_kg} kg chargeable</span>
          </h3>
          <dl className="text-sm">
            {s.quote.breakdown.map((b, i) => (
              <div key={i} className="border-rule flex justify-between gap-4 border-b border-dotted py-1.5">
                <dt className="text-ink-2 tabular-nums">{b.label}</dt>
                <dd className="text-ink tabular-nums">{money(b.amount, s.quote!.currency)}</dd>
              </div>
            ))}
            <div className="flex justify-between gap-4 pt-2">
              <dt className="text-ink font-semibold">All-in total</dt>
              <dd className="text-ink font-bold tabular-nums">{money(s.quote.total, s.quote.currency)}</dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  );
}
