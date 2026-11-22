import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// KPI card after shadcn/ui's dashboard-01 "section cards" block: label + trend badge, big reading, two-line footer.
export type Tone = "good" | "bad" | "warn" | "neutral";
const TONE: Record<Tone, string> = {
  good: "border-[oklch(0.76_0.15_155/0.35)] text-ok",
  bad: "border-signal/50 text-signal-text",
  warn: "border-[oklch(0.8_0.14_70/0.4)] text-late-text",
  neutral: "border-rule-strong text-ink-2",
};

export function KpiCard({
  label,
  value,
  valueClass,
  badge,
  tone = "neutral",
  icon: Icon,
  foot,
  sub,
  className,
}: {
  label: string;
  value: React.ReactNode;
  valueClass?: string;
  badge?: React.ReactNode;
  tone?: Tone;
  icon?: LucideIcon;
  foot?: React.ReactNode;
  sub?: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={cn("kpi-card gap-3 border-rule py-4", className)}>
      <div className="flex items-start justify-between gap-3 px-5">
        <p className="caption pt-1">{label}</p>
        {badge && (
          <Badge variant="outline" className={cn("bg-paper/60 font-semibold tabular-nums", TONE[tone])}>
            {Icon && <Icon />}
            {badge}
          </Badge>
        )}
      </div>
      <p className={cn("font-condensed text-ink px-5 text-[2.75rem] leading-none font-bold tracking-tight tabular-nums", valueClass)}>{value}</p>
      {(foot || sub) && (
        <div className="flex flex-col gap-0.5 px-5 text-sm">
          {foot && <p className="text-ink font-medium">{foot}</p>}
          {sub && <p className="text-ink-3">{sub}</p>}
        </div>
      )}
    </Card>
  );
}
