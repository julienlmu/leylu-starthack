import { Field, FieldStrip, Empty } from "./parts";
import { day, pieceCount, totalWeight } from "@/lib/format";
import type { Session } from "@/lib/types";

export function RequestStrip({ session: s }: { session: Session }) {
  const r = s.rfq;
  if (!r) {
    return (
      <Empty title="Not extracted yet">
        The agent is reading the customer&apos;s mail. Route, pieces and the cheapest-or-fastest ask appear here once it has them.
      </Empty>
    );
  }
  const chargeable = s.quote?.chargeable_weight_kg ?? s.bids[0]?.chargeable_weight_kg ?? null;
  return (
    <FieldStrip className="grid-cols-2 @xl:grid-cols-4 @5xl:grid-cols-6">
      <Field label="Route" className="@5xl:col-span-1">
        <span className="font-condensed text-xl leading-none font-bold tracking-wide">
          {r.origin} <span className="text-ink-3">→</span> {r.destination}
        </span>
      </Field>
      <Field label="Ask">
        <span className="capitalize">{r.ask}</span>
      </Field>
      <Field label="Pieces" className="col-span-2">
        <ul className="flex flex-col gap-0.5">
          {r.pieces.map((p, i) => (
            <li key={i} className="tabular-nums">
              {p.count} × {p.length_cm}×{p.width_cm}×{p.height_cm} cm, {p.weight_kg} kg each
            </li>
          ))}
        </ul>
      </Field>
      <Field label="Weight">
        <span className="tabular-nums">
          {totalWeight(s)} kg actual
          {chargeable !== null && (
            <span className="text-ink-2 block text-sm">{chargeable} kg chargeable</span>
          )}
          {r.volume_m3 ? <span className="text-ink-2 block text-sm">{r.volume_m3} m³ given</span> : null}
        </span>
      </Field>
      <Field label="Ready">{day(r.ready_date)}</Field>
      <Field label="Pickup" className="col-span-2">
        {r.pickup ? (
          <>
            {r.pickup.address}
            <span className={r.pickup.zone ? "text-ink-2 block text-sm" : "text-signal-text block text-sm font-semibold"}>
              {r.pickup.zone ? `Zone ${r.pickup.zone}` : "No pickup zone found"}
            </span>
          </>
        ) : (
          <>
            Delivered to {r.origin} airport
            <span className="text-ink-2 block text-sm">No pickup</span>
          </>
        )}
      </Field>
      <Field label="Commodity">{r.commodity}</Field>
      <Field label="Dangerous goods" tone={r.dangerous_goods ? "alert" : undefined}>
        {r.dangerous_goods ? "Yes" : "No"}
      </Field>
      <Field label="Customer ref">
        {r.customer_reference ? <span className="font-mono text-sm">{r.customer_reference}</span> : <span className="text-ink-3">none given</span>}
      </Field>
      <Field label="Language">
        <span className="uppercase">{r.language}</span>
        <span className="text-ink-2 ml-1.5 text-sm">· {pieceCount(s)} pcs total</span>
      </Field>
    </FieldStrip>
  );
}
