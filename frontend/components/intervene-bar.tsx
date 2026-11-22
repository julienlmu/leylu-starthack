import { useState } from "react";
import { Pause, Play, Send, SquarePen, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { BackendError, intervene } from "@/lib/api";
import { mailOf } from "@/lib/format";
import type { LiveData } from "@/lib/live";
import { cn } from "@/lib/utils";
import type { Event, Session } from "@/lib/types";

type Props = {
  compose?: boolean; // open the reply box at once ("Reply myself" in the simple view)
  session: Session;
  events: Event[];
  live: boolean;
  apply: LiveData["apply"];
  applySession: LiveData["applySession"];
};

// F3: the operator's controls for one session: pause/resume the agent, or write and send a reply by hand.
export function InterveneBar({ session: s, events, live, apply, applySession, compose = false }: Props) {
  const [composing, setComposing] = useState(compose);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The customer's first mail: its sender gets the reply, its recipient is our team mailbox.
  const firstMail = events.filter((e) => e.kind === "mail_in").map(mailOf).find(Boolean) ?? null;
  const to = firstMail?.from ?? s.customer;
  const ours = firstMail?.to ?? "our mailbox";
  const subject = firstMail ? (firstMail.subject.startsWith("Re:") ? firstMail.subject : `Re: ${firstMail.subject}`) : `Re: your request #${s.id}`;
  const quoted = !!s.quote;

  const run = async (action: "pause" | "resume" | "send") => {
    setBusy(true);
    setError(null);
    try {
      if (live) {
        // A hand-written reply must not race the agent: pause first, or the agent's own quote can still go out
        // seconds later (only the first quote in a thread counts). The backend's `send` does not pause.
        if (action === "send" && !s.paused) applySession(await intervene(s.id, "pause"));
        // The reply is the saved session: show it now instead of waiting for the stream.
        applySession(await intervene(s.id, action, action === "send" ? body : undefined));
      } else {
        const text = action === "send" ? "Reply sent by hand" : action === "pause" ? "Paused by a person" : "Resumed by a person";
        apply(
          {
            session_id: s.id,
            at: new Date().toISOString(),
            kind: "intervened",
            text,
            data: action === "send" ? { from: ours, to, subject, body } : {},
            llm_cost_usd: 0,
          },
          {
            ...s,
            paused: action === "resume" ? false : action === "pause" || action === "send",
            needs_human: action === "send" ? false : s.needs_human,
          },
        );
      }
      if (action === "send") {
        setBody("");
        setComposing(false);
      }
    } catch (e) {
      setError(
        e instanceof BackendError
          ? `The backend refused it (${e.status}${e.detail ? `: ${e.detail}` : ""}). Nothing was sent.`
          : "Could not reach the backend. Nothing was sent.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-label="Operator controls" data-guide="intervene" className={cn("border-rule bg-paper rounded-sm border", s.paused && "hatch text-ink-3")}>
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
            <span>{ours}</span>
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
            <p className="text-ink-3 mr-auto text-sm">
              Goes out in the customer&apos;s thread{s.paused ? "" : "; the agent is paused first"}. It cannot be unsent.
            </p>
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
          {error}
        </p>
      )}
    </section>
  );
}
