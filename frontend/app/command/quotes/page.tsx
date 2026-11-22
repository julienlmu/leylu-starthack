"use client";
import Link from "next/link";
import { useCommand } from "@/components/command/shell";
import { money, responseSeconds } from "@/lib/format";
import { RESPONSE_FULL_S } from "@/lib/metrics";
import type { Session } from "@/lib/types";
import { cargo, fmt, initials, route } from "@/lib/command/derive";

const answer = (s: Session): [string, string] =>
  s.booking || s.outcome === "won" ? ["Accepted", "b-good"]
  : s.outcome === "lost" ? ["Declined", "b-muted"]
  : s.outcome === "expired" ? ["Expired", "b-muted"]
  : ["Waiting", "b-warn"];

export default function Quotes() {
  const data = useCommand();
  const list = (data?.sessions ?? []).filter((s) => s.quote).sort((a, b) => Date.parse(b.quote!.sent_at) - Date.parse(a.quote!.sent_at));
  return (
    <section className="card">
      <div className="scroll">
        <table>
          <thead>
            <tr><th scope="col">Customer</th><th scope="col">Route</th><th scope="col">Airline</th><th scope="col" className="r">All-in</th><th scope="col">Answered in</th><th scope="col">Customer&apos;s answer</th></tr>
          </thead>
          <tbody>
            {list.map((s) => {
              const sec = responseSeconds(s);
              const [label, tone] = answer(s);
              return (
                <tr key={s.id}>
                  <td>
                    <div className="whoc">
                      <span className="av" aria-hidden="true">{initials(s.customer)}</span>
                      <div><Link href={`/command?s=${s.id}`}><b>{s.customer}</b></Link><small>{cargo(s)}</small></div>
                    </div>
                  </td>
                  <td className="mono">{route(s)}</td>
                  <td>{s.quote!.carrier ?? "by hand"}</td>
                  <td className="mono r">{money(s.quote!.total, s.quote!.currency)}</td>
                  <td className={`mono${sec !== null && sec > RESPONSE_FULL_S ? " late" : ""}`}>{sec === null ? "—" : fmt(sec)}</td>
                  <td><span className={`badge ${tone}`}>{label}</span></td>
                </tr>
              );
            })}
            {!list.length && <tr className="empty"><td colSpan={6}>{data ? "No quotes sent yet." : "Loading…"}</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
