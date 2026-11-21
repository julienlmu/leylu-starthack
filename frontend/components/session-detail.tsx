import { Booking } from "./detail/booking";
import { Scoreboard, SessionHead } from "./detail/head";
import { Section } from "./detail/parts";
import { PriceOptions } from "./detail/prices";
import { RequestStrip } from "./detail/request";
import { MailThread } from "./detail/thread";
import { Timeline } from "./detail/timeline";
import { InterveneBar } from "./intervene-bar";
import type { LiveData } from "@/lib/live";
import { usd } from "@/lib/format";
import type { Event, Session } from "@/lib/types";

// One session = one customer request = its CRM record.
type Props = { session: Session; events: Event[]; since: number; live: boolean; apply: LiveData["apply"] };

export function SessionDetail({ session, events, since, live, apply }: Props) {
  const mailCount = events.filter((e) => typeof e.data.body === "string").length;
  return (
    <article
      key={session.id}
      className="animate-in slide-in-from-bottom-1 mx-auto flex w-full max-w-[96rem] flex-col gap-8 px-5 pt-6 pb-16 duration-200 md:px-8"
    >
      <div className="flex flex-col gap-5">
        <SessionHead session={session} events={events} />
        <InterveneBar key={session.id} session={session} events={events} live={live} apply={apply} />
        <Scoreboard session={session} />
      </div>

      <Section title="Request" id="request" aside={session.rfq ? "as the agent extracted it" : undefined}>
        <RequestStrip session={session} />
      </Section>

      <div className="grid gap-8 @4xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <Section title="Mail thread" id="thread" aside={`${mailCount} ${mailCount === 1 ? "mail" : "mails"}`}>
          <MailThread events={events} />
        </Section>
        <Section title="Agent steps" id="steps" aside={usd(session.llm_cost_usd)}>
          <Timeline events={events} startedAt={session.received_at} since={since} />
        </Section>
      </div>

      <div className="grid gap-8 @4xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <Section title="Price options" id="prices" aside={session.bids.length ? `${session.bids.length} collected` : undefined}>
          <PriceOptions session={session} />
        </Section>
        <Section title="Booking" id="booking">
          <Booking session={session} />
        </Section>
      </div>
    </article>
  );
}
