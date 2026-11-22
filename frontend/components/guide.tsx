"use client";
// Step-by-step tour: dims the page, rings the element a step explains ([data-guide=…]) and shows a popover.
// One tour per view (Simple / Detailed): the Guide button opens the tour of the view you are in.
// A step whose element still is not on screen (dashboard page, small window) is shown centred, without a ring.
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { View } from "@/lib/prefs";

type Step = { target?: string[]; title: string; body: string };

// Shared opening of both tours.
const VIEW_STEPS: Step[] = [
  {
    target: ["view"],
    title: "Simple or detailed",
    body: "Simple shows only what needs you, what is being answered and what is done. Detailed shows every request with all the agent's steps. Each view has its own tour; your choice is remembered.",
  },
  {
    target: ["theme"],
    title: "Light or dark",
    body: "Switch between a light and a dark screen. Without a choice it follows your computer's setting.",
  },
];

const END: Step = {
  target: ["guide"],
  title: "That's it",
  body: "Open this tour again any time with the Guide button. It explains the view you are in.",
};

export const SIMPLE_STEPS: Step[] = [
  {
    title: "Welcome to the Leylü forwarder",
    body: "An AI agent answers every air-freight request in this mailbox on its own. This simple view only shows what needs you, what is being answered and what is done. The tour takes a minute.",
  },
  ...VIEW_STEPS,
  {
    target: ["simple-chips"],
    title: "Overview and filters",
    body: "How many requests need you, are being answered, are done today, or were ignored as spam. Click a box to show only those; click it again to show everything. Spam stays hidden unless you pick it.",
  },
  {
    target: ["simple-search"],
    title: "Search",
    body: "Type a customer, a route like MUC JFK or a booking reference to narrow the lists below.",
  },
  {
    target: ["simple-needs", "simple-working"],
    title: "Request cards",
    body: "Each card shows the plain status, the reason in red when it needs you, the progress from Read to Booked and the latest mail each way.",
  },
  {
    target: ["simple-needs", "simple-working"],
    title: "Step in",
    body: "Reply myself answers the customer in your own words. Pause stops the agent in that thread until you resume. Show details opens the full record in the detailed view.",
  },
  {
    target: ["simple-done"],
    title: "Done today",
    body: "Today's answered requests, one line each. Open a line to see the quote, the booking and the last mails without leaving this view.",
  },
  END,
];

export const DETAILED_STEPS: Step[] = [
  {
    title: "Welcome to the Leylü forwarder",
    body: "An AI agent answers every air-freight request in this mailbox: it reads the mail, collects prices and sends one all-in quote. This detailed view shows everything it did and lets you step in. The tour takes two minutes.",
  },
  ...VIEW_STEPS,
  {
    target: ["person"],
    title: "Needs a person",
    body: "How many requests the agent could not answer alone. Red means someone should look now. Click it to see only those.",
  },
  {
    target: ["search"],
    title: "Find a request",
    body: "Type a customer, a route like MUC JFK, a reference, #17, a carrier or a booking number. Press / to jump here from anywhere.",
  },
  {
    target: ["filters"],
    title: "Filters",
    body: "Show only the requests that need a person, one stage of the work, or the spam the agent ignored. The number is how many are in each.",
  },
  {
    target: ["strips"],
    title: "Statuses and colours",
    body: "Each request is one strip. The coloured box shows its stage: blue new, yellow pricing, purple quoted, green booked, teal tracking, grey done or spam. Red and pushed out means it needs a person. J and K move between strips.",
  },
  {
    target: ["head"],
    title: "One request",
    body: "The customer, when the mail came in and the path from new to done. A red bar says why a person is needed; a grey Spam bar says why the mail was ignored.",
  },
  {
    target: ["intervene"],
    title: "Step in",
    body: "Pause stops the agent from sending anything in this thread; Resume hands it back. Reply by hand sends your own mail and pauses the agent first. Use them when the request is red or the agent's reading looks wrong.",
  },
  {
    target: ["scoreboard"],
    title: "Response time and cost",
    body: "How fast the quote went out (full points inside 2:00, none after 6:00), the all-in price sent and what the AI reading cost.",
  },
  {
    target: ["request"],
    title: "What the agent read",
    body: "The shipment as the agent extracted it from the mail: route, pieces, weights, dates and special cargo. Check this first when something looks off.",
  },
  {
    target: ["thread"],
    title: "Mail thread",
    body: "Every mail in and out of this conversation, the customer's on the left and ours on the right.",
  },
  {
    target: ["steps"],
    title: "Agent steps",
    body: "Each step the agent took, with its time since the mail arrived.",
  },
  {
    target: ["prices"],
    title: "Prices and bids",
    body: "Every price collected: rate sheet, portal and carrier bids. The one marked Quoted is what the customer got.",
  },
  {
    target: ["booking"],
    title: "Booking and tracking",
    body: "When the customer accepts, the agent books by rate ID. The booking reference, airline and status updates for tracking questions appear here.",
  },
  {
    target: ["nav-dashboard"],
    title: "Dashboard",
    body: "Tonight's numbers at a glance: average response time, quotes sent, won, cost per quote and outcomes.",
  },
  END,
];

const PAD = 6;

// The first target that is on the page and visible.
const findTarget = (step: Step) => {
  for (const name of step.target ?? []) {
    const el = document.querySelector<HTMLElement>(`[data-guide="${name}"]`);
    if (el && el.getClientRects().length && el.offsetWidth > 0) return el;
  }
  return null;
};

// `tour` is the view the Guide button was clicked in; null when closed. Fixed for the whole tour.
export function Guide({ tour, onClose }: { tour: View | null; onClose: () => void }) {
  const open = tour !== null;
  const steps = tour === "simple" ? SIMPLE_STEPS : DETAILED_STEPS;
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const returnTo = useRef<HTMLElement | null>(null);
  const step = steps[i] ?? steps[0];
  const last = i === steps.length - 1;

  const close = useCallback(() => {
    onClose();
    setI(0);
    returnTo.current?.focus();
  }, [onClose]);

  useEffect(() => {
    if (open) returnTo.current = document.activeElement as HTMLElement | null;
  }, [open]);

  // Wait until the step's element is rendered, scroll it in, then follow scrolling and resizing.
  useLayoutEffect(() => {
    if (!open) return;
    let el: HTMLElement | null = null;
    let frame = 0;
    let tries = 0;
    const measure = () => {
      if (!el) return setRect(null);
      const b = el.getBoundingClientRect();
      const top = Math.max(b.top, 0);  // the ring is clipped to the window, so a tall target leaves room for the popover
      const bottom = Math.min(b.bottom, window.innerHeight);
      setRect(new DOMRect(b.left, top, b.width, Math.max(0, bottom - top)));
    };
    const find = () => {
      el = findTarget(step);
      if (!el && step.target?.length && tries++ < 60) {  // up to ~1 s: a session's details still rendering
        frame = requestAnimationFrame(find);
        return;
      }
      const r = el?.getBoundingClientRect();
      // Only scroll what is off screen and fits: scrolling a tall list would also push the top bar away.
      if (el && r && (r.top < 0 || r.bottom > window.innerHeight) && r.height < window.innerHeight - 80) {
        el.scrollIntoView({ block: "center", behavior: "instant" as ScrollBehavior });
      }
      measure();
    };
    setRect(null);
    find();
    nextRef.current?.focus();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [open, step]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      } else if (e.key === "ArrowRight" && !last) setI((n) => n + 1);
      else if (e.key === "ArrowLeft") setI((n) => Math.max(0, n - 1));
      else if (e.key === "Tab") {
        // keep focus inside the popover
        const items = popRef.current?.querySelectorAll<HTMLElement>("button");
        if (!items?.length) return;
        const first = items[0];
        const end = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          end.focus();
        } else if (!e.shiftKey && document.activeElement === end) {
          e.preventDefault();
          first.focus();
        } else if (!popRef.current?.contains(document.activeElement)) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, last, close]);

  if (!open) return null;

  // Popover under the ring, else above, else beside it, else at the bottom edge; centred when there is no ring.
  const W = Math.min(360, window.innerWidth - 32);
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const GAP = PAD + 10;
  const NEED = 300; // the popover's height with a 3-sentence step, roughly
  const left = rect ? Math.min(Math.max(16, rect.left), vw - W - 16) : 0;
  const style: React.CSSProperties = !rect
    ? { width: W, left: "50%", top: "50%", transform: "translate(-50%, -50%)" }
    : vh - rect.bottom >= NEED + GAP
      ? { width: W, left, top: rect.bottom + GAP }
      : rect.top >= NEED + GAP
        ? { width: W, left, bottom: vh - rect.top + GAP }
        : vw - rect.right >= W + GAP + 16
          ? { width: W, left: rect.right + GAP, top: Math.min(Math.max(16, rect.top), vh - NEED - 16) }
          : rect.left >= W + GAP + 16
            ? { width: W, left: rect.left - GAP - W, top: Math.min(Math.max(16, rect.top), vh - NEED - 16) }
            : { width: W, left: (vw - W) / 2, bottom: 16 };

  return (
    <div className="fixed inset-0 z-50">
      {rect ? (
        <div
          aria-hidden
          className="pointer-events-none fixed rounded-sm ring-2 ring-[var(--st-pricing)] transition-all duration-200"
          style={{
            left: rect.left - PAD,
            top: rect.top - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            boxShadow: "0 0 0 9999px oklch(0.1 0.02 256 / 0.62)",
          }}
        />
      ) : (
        <div aria-hidden className="fixed inset-0 bg-[oklch(0.1_0.02_256/0.62)]" />
      )}
      {/* clicks on the dimmed page do nothing: the tour ends with Done, Skip or Escape */}
      <div className="fixed inset-0" onClick={(e) => e.stopPropagation()} />
      <div
        ref={popRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="guide-title"
        aria-describedby="guide-body"
        className="bg-paper text-ink border-rule-strong fixed flex flex-col gap-3 rounded-sm border p-4 shadow-xl"
        style={style}
      >
        <p className="caption">
          {tour === "simple" ? "Simple" : "Detailed"} view tour · Step {i + 1} of {steps.length}
        </p>
        <h2 id="guide-title" className="text-lg leading-tight font-semibold">
          {step.title}
        </h2>
        <p id="guide-body" className="text-ink-2 text-[0.9375rem] leading-relaxed">
          {step.body}
        </p>
        <div className="flex items-center gap-2 pt-1">
          <Button size="sm" variant="ghost" onClick={close} className="mr-auto">
            {last ? "Close" : "Skip tour"}
          </Button>
          {i > 0 && (
            <Button size="sm" variant="outline" onClick={() => setI(i - 1)} className="bg-paper">
              Back
            </Button>
          )}
          <Button ref={nextRef} size="sm" onClick={() => (last ? close() : setI(i + 1))}>
            {last ? "Done" : "Next"}
          </Button>
        </div>
      </div>
    </div>
  );
}

