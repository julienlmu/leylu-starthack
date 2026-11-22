import { cn } from "@/lib/utils";
import { outcomeLabel } from "@/lib/format";
import type { Outcome } from "@/lib/types";
import { outcomeVar } from "@/lib/v2/view";

// Colour plus the word: never colour alone.
export function OutcomeChip({ outcome, className }: { outcome: Outcome; className?: string }) {
  return (
    <span className={cn("rounded-sm px-2 py-0.5 text-xs font-bold tracking-wide uppercase", outcomeVar[outcome], className)}>
      {outcomeLabel[outcome]}
    </span>
  );
}
