import { AlertTriangle, Pause } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { clock, duration, money, outcomeStyle, responseSeconds, stageStyle, usd } from "@/lib/format";
import type { Event, PriceOption, Session } from "@/lib/types";

type Mail = { from: string; to: string; subject: string; body: string };
const asMail = (e: Event): Mail | null => (typeof e.data?.body === "string" ? (e.data as Mail) : null);

const sameOption = (a: PriceOption, b: PriceOption | null) =>
  !!b && a.carrier === b.carrier && a.source === b.source && a.total === b.total;

export function SessionDetail({ session: s, events }: { session: Session; events: Event[] }) {
  const rt = responseSeconds(s);
  const mails = events.filter((e) => asMail(e));
  const pieces = s.rfq?.pieces ?? [];
  const actualKg = pieces.reduce((sum, p) => sum + p.count * p.weight_kg, 0);

  return (
    <div className="space-y-4 p-5">
      {/* Header */}
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-muted-foreground font-mono text-xs">
            #{s.id} · thread {s.thread_id} · received {clock(s.received_at)}
          </div>
          <h2 className="truncate text-xl font-semibold">{s.customer}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className={cn("rounded px-2 py-0.5 font-medium", stageStyle[s.stage])}>{s.stage}</span>
          <span className={cn("font-medium capitalize", outcomeStyle[s.outcome])}>{s.outcome}</span>
        </div>
      </div>

      {(s.needs_human || s.paused) && (
        <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {s.paused ? <Pause className="size-4" /> : <AlertTriangle className="size-4" />}
          {s.needs_human ? "Needs a person." : ""} {s.paused ? "Agent paused for this session." : ""}
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Response time" value={rt !== null ? duration(rt) : "—"} hint={rt === null ? "no quote yet" : rt <= 120 ? "full points" : "losing points"} tone={rt === null ? undefined : rt <= 120 ? "good" : "warn"} />
        <Stat label="Quote" value={s.quote ? money(s.quote.total, s.quote.currency) : "—"} hint={s.quote ? `${s.quote.carrier} · ${s.quote.transit_days} d` : "not sent"} />
        <Stat label="LLM cost" value={usd(s.llm_cost_usd)} hint={s.llm_cost_usd < 0.1 ? "under $0.10 cap" : "over cap"} tone={s.llm_cost_usd < 0.1 ? "good" : "warn"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {/* Left: what happened */}
        <div className="space-y-4">
          <Card className="gap-3 py-4">
            <CardHeader className="px-4"><CardTitle className="text-sm">Mail thread</CardTitle></CardHeader>
            <CardContent className="space-y-3 px-4">
              {mails.length === 0 && <p className="text-muted-foreground text-sm">No mails yet.</p>}
              {mails.map((e, i) => {
                const m = asMail(e)!;
                const ours = e.kind !== "mail_in" && e.kind !== "accepted";
                return (
                  <div key={i} className={cn("rounded-md border p-3", ours ? "ml-6 bg-sky-50/60" : "mr-6")}>
                    <div className="text-muted-foreground mb-1 flex gap-2 font-mono text-[11px]">
                      <span className="truncate">{m.from} → {m.to}</span>
                      <span className="ml-auto shrink-0">{clock(e.at)}</span>
                    </div>
                    <div className="mb-1 text-sm font-medium">{m.subject}</div>
                    <p className="text-sm whitespace-pre-line">{m.body}</p>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          <Card className="gap-3 py-4">
            <CardHeader className="px-4"><CardTitle className="text-sm">Steps</CardTitle></CardHeader>
            <CardContent className="px-4">
              <ol className="space-y-1.5">
                {events.map((e, i) => (
                  <li key={i} className="flex gap-3 text-sm">
                    <span className="text-muted-foreground w-16 shrink-0 font-mono text-xs leading-5">{clock(e.at)}</span>
                    <span className={cn("w-28 shrink-0 font-mono text-xs leading-5", e.kind === "error" || e.kind === "needs_human" ? "text-red-700" : "text-muted-foreground")}>{e.kind}</span>
                    <span className="flex-1">{e.text}</span>
                    {e.llm_cost_usd > 0 && <span className="text-muted-foreground font-mono text-xs leading-5">{usd(e.llm_cost_usd)}</span>}
                  </li>
                ))}
                {events.length === 0 && <li className="text-muted-foreground text-sm">No steps yet.</li>}
              </ol>
            </CardContent>
          </Card>
        </div>

        {/* Right: the data */}
        <div className="space-y-4">
          <Card className="gap-3 py-4">
            <CardHeader className="px-4"><CardTitle className="text-sm">Extracted request</CardTitle></CardHeader>
            <CardContent className="px-4">
              {!s.rfq ? (
                <p className="text-muted-foreground text-sm">Not extracted yet.</p>
              ) : (
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                  <Row k="Route" v={`${s.rfq.origin} → ${s.rfq.destination}`} />
                  <Row k="Customer wants" v={s.rfq.ask} />
                  <Row k="Pickup" v={s.rfq.pickup ? `${s.rfq.pickup.address} (zone ${s.rfq.pickup.zone ?? "unknown"})` : "airport delivery"} />
                  <Row k="Ready" v={s.rfq.ready_date} />
                  <Row k="Pieces" v={pieces.map((p) => `${p.count} × ${p.length_cm}×${p.width_cm}×${p.height_cm} cm, ${p.weight_kg} kg`).join("; ")} />
                  <Row k="Actual weight" v={`${actualKg} kg`} />
                  <Row k="Commodity" v={s.rfq.commodity + (s.rfq.dangerous_goods ? " ⚠ dangerous goods" : "")} />
                  <Row k="Reference" v={s.rfq.customer_reference ?? "—"} />
                  <Row k="Language" v={s.rfq.language} />
                </dl>
              )}
            </CardContent>
          </Card>

          <Card className="gap-3 py-4">
            <CardHeader className="px-4"><CardTitle className="text-sm">Options ({s.bids.length})</CardTitle></CardHeader>
            <CardContent className="px-4">
              {s.bids.length === 0 ? (
                <p className="text-muted-foreground text-sm">No prices yet.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="text-muted-foreground text-left text-xs">
                    <tr><th className="pb-1 font-normal">Carrier</th><th className="pb-1 font-normal">Source</th><th className="pb-1 text-right font-normal">Transit</th><th className="pb-1 text-right font-normal">All-in</th></tr>
                  </thead>
                  <tbody>
                    {[...s.bids].sort((a, b) => a.total - b.total).map((o, i) => {
                      const chosen = sameOption(o, s.quote);
                      return (
                        <tr key={i} className={cn("border-t", chosen && "bg-emerald-50 font-medium")}>
                          <td className="py-1.5">{o.carrier}{chosen && <span className="ml-2 text-xs text-emerald-700">quoted</span>}</td>
                          <td className="text-muted-foreground py-1.5 font-mono text-xs">{o.source}</td>
                          <td className="py-1.5 text-right">{o.transit_days} d</td>
                          <td className="py-1.5 text-right font-mono">{money(o.total, o.currency)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>

          {s.quote && (
            <Card className="gap-3 py-4">
              <CardHeader className="px-4">
                <CardTitle className="text-sm">Quote sent {clock(s.quote.sent_at)}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 px-4 text-sm">
                {s.quote.breakdown.map((b, i) => (
                  <div key={i} className="flex justify-between"><span className="text-muted-foreground">{b.label}</span><span className="font-mono">{money(b.amount, s.quote!.currency)}</span></div>
                ))}
                <div className="flex justify-between border-t pt-1 font-semibold"><span>All-in total</span><span className="font-mono">{money(s.quote.total, s.quote.currency)}</span></div>
                <div className="text-muted-foreground text-xs">
                  {s.quote.chargeable_weight_kg} kg chargeable · rate {s.quote.rate_id ?? "from sheet"}
                </div>
              </CardContent>
            </Card>
          )}

          <Card className="gap-3 py-4">
            <CardHeader className="px-4"><CardTitle className="text-sm">Booking</CardTitle></CardHeader>
            <CardContent className="space-y-2 px-4 text-sm">
              {!s.booking ? (
                <p className="text-muted-foreground">Not booked.</p>
              ) : (
                <div className="font-mono text-xs">
                  {[
                    s.booking.booking_reference ?? s.booking.confirmation,
                    s.booking.airline,
                    `rate ${s.booking.rate_id}`,
                    s.booking.status,
                    s.booking.booked_at && clock(s.booking.booked_at),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              )}
              {s.status_updates.map((u, i) => (
                <div key={i} className="flex gap-3"><span className="text-muted-foreground font-mono text-xs">{clock(u.at)}</span><span>{u.text}</span></div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: "good" | "warn" }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="text-muted-foreground text-xs">{label}</div>
      <div className="mt-0.5 font-mono text-lg font-semibold">{value}</div>
      <div className={cn("text-xs", tone === "good" ? "text-emerald-700" : tone === "warn" ? "text-amber-700" : "text-muted-foreground")}>{hint}</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <>
      <dt className="text-muted-foreground">{k}</dt>
      <dd>{v}</dd>
    </>
  );
}
