import { Empty, Field, FieldStrip } from "./parts";
import { clock } from "@/lib/format";
import type { Session } from "@/lib/types";

export function Booking({ session: s }: { session: Session }) {
  const b = s.booking;
  return (
    <div className="flex flex-col gap-5">
      {b ? (
        <FieldStrip className="grid-cols-2">
          <Field label="AWB / confirmation">
            <span className="font-mono text-sm">{b.confirmation ?? "pending"}</span>
          </Field>
          <Field label="Booking ref">
            <span className="font-mono text-sm">{b.booking_reference ?? "–"}</span>
          </Field>
          <Field label="Airline">{b.airline ?? s.quote?.carrier ?? "–"}</Field>
          <Field label="Rate ID">
            <span className="font-mono text-sm">{b.rate_id}</span>
          </Field>
          <Field label="Booked at">{b.booked_at ? <span className="tabular-nums">{clock(b.booked_at)}</span> : "–"}</Field>
          <Field label="Status">
            <span className="capitalize">{b.status ?? "–"}</span>
          </Field>
        </FieldStrip>
      ) : (
        <Empty title="Not booked">
          {s.outcome === "lost" || s.outcome === "expired"
            ? `The customer did not take this quote (${s.outcome}).`
            : "When the customer accepts, the agent books the quoted rate by its ID and the confirmation appears here."}
        </Empty>
      )}

      <div>
        <h3 className="text-ink mb-2 text-sm font-semibold">Status updates</h3>
        {s.status_updates.length ? (
          <ol className="flex flex-col">
            {s.status_updates.map((u, i) => (
              <li key={i} className="border-rule flex gap-3 border-b py-2 text-sm last:border-b-0">
                <span className="text-ink-2 w-16 shrink-0 tabular-nums">{clock(u.at)}</span>
                <span className="text-ink">{u.text}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-ink-3 text-sm">None sent yet.</p>
        )}
      </div>
    </div>
  );
}
