import { ArrowDownLeft, ArrowUpRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Empty } from "./parts";
import { clock, isOurs, kindLabel, mailOf } from "@/lib/format";
import type { Event } from "@/lib/types";

// The thread exactly as the customer sees it: their mails and our replies, oldest first.
export function MailThread({ events }: { events: Event[] }) {
  const mails = events.flatMap((e) => {
    const m = mailOf(e);
    return m ? [{ e, m }] : [];
  });
  if (!mails.length) {
    return <Empty title="No mail yet">Incoming customer mail and every reply we send in this thread show up here.</Empty>;
  }
  return (
    <ol className="flex flex-col gap-3">
      {mails.map(({ e, m }, i) => {
        const ours = isOurs(e);
        return (
          <li
            key={`${e.at}-${i}`}
            className={cn(
              "border-rule overflow-hidden rounded-sm border",
              ours ? "bg-ours @3xl:ml-8" : "bg-paper @3xl:mr-8",
            )}
          >
            <div className={cn("border-rule flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2.5", ours && "border-ours-rule")}>
              <span
                className={cn(
                  "font-condensed flex items-center gap-1 rounded-[2px] px-1.5 py-0.5 text-xs font-bold tracking-[0.06em] uppercase",
                  ours ? "bg-console text-console-ink" : "bg-[var(--st-new)] text-[var(--st-new-ink)]",
                )}
              >
                {ours ? <ArrowUpRight className="size-3.5" aria-hidden /> : <ArrowDownLeft className="size-3.5" aria-hidden />}
                {ours ? "Leylü" : "Customer"}
              </span>
              <span className="text-ink-2 min-w-0 truncate font-mono text-xs">
                {m.from} → {m.to}
              </span>
              <span className="text-ink-3 ml-auto text-sm tabular-nums">
                {kindLabel[e.kind]} · {clock(e.at)}
              </span>
            </div>
            <div className="px-4 pt-3 pb-4">
              <p className="text-ink mb-2 font-semibold">{m.subject}</p>
              <p className="text-ink max-w-[68ch] text-[0.9375rem] leading-relaxed whitespace-pre-line">{m.body}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
