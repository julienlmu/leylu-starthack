"use client";
import Link from "next/link";
import { useEffect } from "react";
import { useCommand } from "@/components/command/shell";
import { clock } from "@/lib/format";
import type { Session } from "@/lib/types";
import { thread } from "@/lib/command/derive";

// Q&A cards: the customer's tracking question (the mail_in before a tracking_answer) and our answer.
// Booked sessions without a question show the last status we sent.
export default function Tracking() {
  const data = useCommand();
  const loadEvents = data?.loadEvents;
  const list = (data?.sessions ?? []).filter((s) => s.stage === "tracking" || s.status_updates.length > 0);
  const ids = list.map((s) => s.id).join(",");
  useEffect(() => {
    if (loadEvents && ids) ids.split(",").forEach((id) => loadEvents(Number(id)));
  }, [ids, loadEvents]);
  if (!data) return <p className="hint">Loading…</p>;

  const card = (s: Session) => {
    const ev = data.events.filter((e) => e.session_id === s.id);
    const answer = ev.filter((e) => e.kind === "tracking_answer").at(-1);
    const msgs = thread(data.events, s.id);
    const question = answer ? msgs.filter((m) => !m.ours && Date.parse(m.at) <= Date.parse(answer.at)).at(-1) : undefined;
    const reply = answer ? msgs.find((m) => m.at === answer.at && m.ours) : undefined;
    const status = s.status_updates.at(-1);
    return { s, question, reply, answer, status, at: answer?.at ?? status?.at ?? s.received_at };
  };
  const cards = list.map(card).sort((a, b) => Date.parse(b.at) - Date.parse(a.at));

  if (!cards.length) return <section className="card"><p className="empty">No tracking questions yet. They appear here once a booked customer asks where the shipment is.</p></section>;
  return (
    <div className="grid2">
      {cards.map(({ s, question, reply, answer, status }) => (
        <section key={s.id} className="card pad" aria-label={`Tracking for ${s.customer}`}>
          <h2><Link href={`/command?s=${s.id}`}>{s.customer} · {s.booking?.booking_reference ?? s.booking?.confirmation ?? `#${s.id}`}</Link></h2>
          {question && <div className="msg"><small>Customer asked · {clock(question.at)}</small>{question.mail.body.trim()}</div>}
          {answer && <div className="msg ours"><small>Leylü answered · {clock(answer.at)}</small>{reply?.mail.body.trim() ?? answer.text}</div>}
          {!answer && status && <div className="msg ours"><small>Leylü sent · {clock(status.at)}</small>{status.text}</div>}
          {!answer && !status && <p className="hint">{data.live ? "Loading…" : "No answer stored."}</p>}
        </section>
      ))}
    </div>
  );
}
