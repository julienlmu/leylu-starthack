"use client";
import Link from "next/link";
import { useCommand } from "@/components/command/shell";
import { clock, money } from "@/lib/format";
import { route } from "@/lib/command/derive";

export default function Bookings() {
  const data = useCommand();
  const when = (b: { booked_at?: string } | null, fallback: string) => Date.parse(b?.booked_at ?? fallback);
  const list = (data?.sessions ?? []).filter((s) => s.booking).sort((a, b) => when(b.booking, b.received_at) - when(a.booking, a.received_at));
  return (
    <section className="card">
      <div className="scroll">
        <table>
          <thead>
            <tr><th scope="col">Booking</th><th scope="col">Customer</th><th scope="col">Route</th><th scope="col">Airline</th><th scope="col">Booked</th><th scope="col" className="r">All-in</th><th scope="col">Airline confirmation</th></tr>
          </thead>
          <tbody>
            {list.map((s) => {
              const b = s.booking!;
              const ok = b.status === "confirmed";
              return (
                <tr key={s.id}>
                  <td className="mono"><Link href={`/command?s=${s.id}`}>{b.booking_reference ?? b.rate_id}</Link></td>
                  <td><b>{s.customer}</b></td>
                  <td className="mono">{route(s)}</td>
                  <td>{b.airline ?? s.quote?.carrier ?? "—"}</td>
                  <td className="mono">{b.booked_at ? clock(b.booked_at) : "—"}</td>
                  <td className="mono r">{s.quote ? money(s.quote.total, s.quote.currency) : "—"}</td>
                  <td>
                    <span className={`badge ${ok ? "b-good" : "b-warn"}`}>{ok ? "Confirmed" : b.status || "Waiting"}</span>
                    {b.confirmation && <span className="mono"> {b.confirmation}</span>}
                  </td>
                </tr>
              );
            })}
            {!list.length && <tr className="empty"><td colSpan={7}>{data ? "No bookings yet." : "Loading…"}</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
