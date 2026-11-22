import { cn } from "@/lib/utils";
import { airOptions, clock, isOurs, mailOf, money, sameOption, sourceLabel, transit, type Mail } from "@/lib/format";
import type { Event, Session } from "@/lib/types";
import { notes } from "@/lib/v2/view";

// Detail: customer mail beside our reply, the price options, the gate notes.
export function Detail({ session: s, events }: { session: Session; events: Event[] }) {
  return (
    <div className="flex flex-col gap-3">
      <Thread events={events} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Prices session={s} events={events} />
        <GateNotes events={events} />
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="bg-(--v2-surface) border-(--v2-rule) rounded-md border px-4 py-3">
      <h3 className="text-(--v2-ink-2) mb-2 text-xs font-bold tracking-wide uppercase">{title}</h3>
      {children}
    </section>
  );
}

// Each customer mail paired with the reply we sent after it.
function Thread({ events }: { events: Event[] }) {
  const pairs: { in?: { e: Event; m: Mail }; out?: { e: Event; m: Mail } }[] = [];
  for (const e of events) {
    const m = mailOf(e);
    if (!m) continue;
    const last = pairs[pairs.length - 1];
    // accepted/declined carry the customer's mail when they carry one (mock data does); format.isOurs counts them as ours.
    if (!isOurs(e) || e.kind === "accepted" || e.kind === "declined") pairs.push({ in: { e, m } });
    else if (last && !last.out) last.out = { e, m };
    else pairs.push({ out: { e, m } });
  }
  return (
    <Section title="Customer mail and our reply">
      {!pairs.length && <p className="text-(--v2-ink-2)">No mail in this thread yet.</p>}
      <div className="flex flex-col gap-3">
        {pairs.map((p, i) => (
          <div key={i} className="grid gap-3 md:grid-cols-2">
            <MailCard who="Customer" mail={p.in} />
            <MailCard who="Our reply" mail={p.out} ours />
          </div>
        ))}
      </div>
    </Section>
  );
}

function MailCard({ who, mail, ours }: { who: string; mail?: { e: Event; m: Mail }; ours?: boolean }) {
  return (
    <article className={cn("border-(--v2-rule) min-w-0 rounded-md border p-3", ours ? "bg-(--v2-ours)" : "bg-(--v2-surface-2)")}>
      <header className="text-(--v2-ink-2) mb-1 flex gap-2 text-xs">
        <span className="font-bold tracking-wide uppercase">{who}</span>
        {mail && <span className="ml-auto font-mono">{clock(mail.e.at)}</span>}
      </header>
      {mail ? (
        <>
          <p className="mb-1 font-semibold">{mail.m.subject}</p>
          <p tabIndex={0} aria-label={`${who}: ${mail.m.subject}`} className="max-h-28 overflow-y-auto text-sm leading-snug whitespace-pre-line">{mail.m.body}</p>
        </>
      ) : (
        <p className="text-(--v2-ink-2) text-sm">{ours ? "No reply yet." : "–"}</p>
      )}
    </article>
  );
}

function Prices({ session: s, events }: { session: Session; events: Event[] }) {
  const options = airOptions(s.bids);
  if (s.quote && !options.some((o) => sameOption(o, s.quote!))) options.push(s.quote);
  options.sort((a, b) => a.total - b.total);
  // The agent says "REMEMBERED portal rates" in its priced event when the portal was down and memory priced it.
  const remembered = events.some((e) => e.kind === "priced" && /remembered/i.test(e.text));
  const source = (o: (typeof options)[number]) =>
    o.source === "portal" && remembered ? "Portal (remembered)" : o.source === "carrier_bid" ? "Bid" : sourceLabel[o.source];
  return (
    <Section title="Price options">
      {!options.length ? (
        <p className="text-(--v2-ink-2)">No prices yet.</p>
      ) : (
        <table className="w-full text-sm">
          <caption className="sr-only">Price options, lowest first; the chosen one is marked</caption>
          <thead className="text-(--v2-ink-2) text-left text-xs uppercase">
            <tr>
              <th scope="col" className="py-1">Carrier</th>
              <th scope="col">Source</th>
              <th scope="col" className="text-right">Transit</th>
              <th scope="col" className="text-right">All-in</th>
            </tr>
          </thead>
          <tbody>
            {options.map((o, i) => {
              const chosen = !!s.quote && sameOption(o, s.quote);
              return (
                <tr key={i} className={cn("border-(--v2-rule) border-t", chosen && "bg-(--v2-chosen) font-semibold")}>
                  <th scope="row" className="py-1.5 pl-1 text-left font-medium">
                    {chosen && <span className="mr-1.5 rounded-sm bg-(--v2-won) px-1 text-xs font-bold text-(--v2-won-ink)">CHOSEN</span>}
                    {o.carrier}
                  </th>
                  <td>{source(o)}{o.rate_id && <span className="text-(--v2-ink-2) font-mono text-xs"> · {o.rate_id}</span>}</td>
                  <td className="text-right tabular-nums">{transit(o.transit_days)}</td>
                  <td className="pr-1 text-right tabular-nums">{money(o.total, o.currency)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Section>
  );
}

const levelStyle: Record<string, string> = {
  hold: "bg-(--v2-late) text-black",
  person: "bg-(--v2-signal) text-white",
  error: "bg-(--v2-signal) text-white",
  fix: "bg-(--v2-open) text-white",
};

function GateNotes({ events }: { events: Event[] }) {
  const list = notes(events);
  return (
    <Section title="Gate notes and flags">
      {!list.length ? (
        <p className="text-(--v2-ink-2) text-sm">Nothing flagged for this session.</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {list.map((n, i) => (
            <li key={i} className="flex gap-2">
              <span className={cn("h-fit shrink-0 rounded-sm px-1.5 text-xs font-bold uppercase", levelStyle[n.level] ?? "border-(--v2-rule) border")}>
                {n.level === "person" ? "needs a person" : n.level}
              </span>
              <span>{n.text}</span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
