import { useState } from "react";
import { Pause, Play, Send, SquarePen, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { intervene } from "@/lib/api";
import { mailOf } from "@/lib/format";
import type { LiveData } from "@/lib/live";
import { cn } from "@/lib/utils";
import type { Event, Session } from "@/lib/types";

const OUR_ADDRESS = "quotes@leylu.air"; // display only; the agent sends from the team mailbox

type Props = { session: Session; events: Event[]; live: boolean; apply: LiveData["apply"] };

// F3: the operator's controls for one session: pause/resume the agent, or write and send a reply by hand.
export function InterveneBar({ session: s, events, live, apply }: Props) {
  const [composing, setComposing] = useState(false);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const firstMail = events.map(mailOf).find((m) => m && !m.from.endsWith("@leylu.air"));
  const to = firstMail?.from ?? s.customer;
  const subject = firstMail ? (firstMail.subject.startsWith("Re:") ? firstMail.subject : `Re: ${firstMail.subject}`) : `Re: your request #${s.id}`;
  const quoted = !!s.quote;

  const run = async (action: "pause" | "resume" | "send") => {
    setBusy(true);
    setError(null);
    try {
      // Live: the backend records it; the stream brings the event and the new session state back.
      if (live) await intervene(s.id, action, action === "send" ? body : undefined);
      else {
        const text = action === "send" ? "Reply sent by hand" : action === "pause" ? "Paused by a person" : "Resumed by a person";
        apply(
          {
            session_id: s.id,
            at: new Date().toISOString(),
            kind: "intervened",
            text,
            data: action === "send" ? { from: OUR_ADDRESS, to, subject, body } : {},
            llm_cost_usd: 0,
          },
          {
            ...s,
            paused: action === "pause" ? true : action === "resume" ? false : s.paused,
            needs_human: action === "send" ? false : s.needs_human,
          },
        );
      }
      if (action === "send") {
        setBody("");
        setComposing(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="Operator controls" className={cn("border-rule bg-paper rounded-sm border", s.paused && "hatch text-ink-3")}>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="caption">Operator</p>
          <p className="text-ink text-[0.9375rem] font-medium">
            {s.paused ? "Agent paused: nothing goes out in this thread until you resume it." : "The agent is handling this session."}
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={busy} onClick={() => run(s.paused ? "resume" : "pause")} className="bg-paper">
            {s.paused ? <Play /> : <Pause />}
            {s.paused ? "Resume agent" : "Pause agent"}
          </Button>
          {!composing && (
            <Button size="sm" disabled={busy} onClick={() => setComposing(true)}>
              <SquarePen />
              Reply by hand
            </Button>
          )}
        </div>
      </div>

      {composing && (
        <div className="border-rule bg-paper flex flex-col gap-2 border-t px-4 py-3">
          <p className="text-ink-2 flex flex-wrap gap-x-2 font-mono text-[0.8125rem]">
            <span>{OUR_ADDRESS}</span>
            <span aria-hidden>→</span>
            <span className="text-ink">{to}</span>
            <span className="text-ink-3 font-sans">· {subject}</span>
          </p>
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            aria-label={`Reply to ${to}`}
            placeholder={
              quoted
                ? "Write the reply as it should reach the customer."
                : "No quote has gone out yet, so this reply counts as the quote: state one all-in total with its currency."
            }
            rows={6}
            autoFocus
            className="bg-paper text-[0.9375rem]"
          />
          <div className="flex flex-wrap items-center justify-end gap-2">
            <p className="text-ink-3 mr-auto text-sm">Goes out in the customer&apos;s thread. It cannot be unsent.</p>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setComposing(false)}>
              <X />
              Cancel
            </Button>
            <Button size="sm" disabled={busy || !body.trim()} onClick={() => run("send")}>
              <Send />
              Send to {to}
            </Button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-signal-text border-rule border-t px-4 py-2 text-sm font-medium">
          Could not reach the backend ({error}). Nothing was sent.
        </p>
      )}
    </section>
  );
}
