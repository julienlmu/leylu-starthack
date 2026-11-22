import { cn } from "@/lib/utils";

// A section of the session record: heading row plus content, divided by one hairline.
export function Section({
  title,
  aside,
  children,
  className,
  id,
}: {
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  const headingId = id ? `${id}-title` : undefined;
  return (
    <section aria-labelledby={headingId} data-guide={id} className={cn("flex min-w-0 flex-col", className)}>
      <div className="mb-3 flex items-baseline justify-between gap-4">
        <h2 id={headingId} className="text-ink text-base font-semibold tracking-tight">
          {title}
        </h2>
        {aside && <div className="text-ink-3 text-sm tabular-nums">{aside}</div>}
      </div>
      {children}
    </section>
  );
}

// One box of a strip: tiny caption on top, the value under it.
export function Field({
  label,
  children,
  className,
  tone,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
  tone?: "alert";
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5 px-3 py-2.5", tone === "alert" && "bg-signal-wash", className)}>
      <dt className={cn("caption", tone === "alert" && "text-signal-text")}>{label}</dt>
      <dd className={cn("text-ink text-[0.9375rem] leading-snug font-medium", tone === "alert" && "text-signal-text font-semibold")}>
        {children}
      </dd>
    </div>
  );
}

// A grid of fields sharing hairlines, like the boxes printed on a flight strip.
export function FieldStrip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <dl
      className={cn(
        "border-rule bg-rule grid gap-px overflow-hidden rounded-sm border [&>*]:bg-paper",
        className,
      )}
    >
      {children}
    </dl>
  );
}

export function Empty({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border-rule-strong flex flex-col gap-1 rounded-sm border border-dashed px-4 py-4">
      <p className="text-ink text-sm font-semibold">{title}</p>
      <p className="text-ink-2 text-sm">{children}</p>
    </div>
  );
}
