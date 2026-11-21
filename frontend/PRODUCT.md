# Product

<!-- impeccable:product-schema 1 -->

> Written unattended from the team's brief (no interview was possible). Facts below come from
> that brief and from `lib/types.ts`; nothing here was confirmed in a live interview.

## Platform

web

## Users

- **Night-watch operator (primary).** A human supervisor watching an autonomous AI air-freight
  forwarder overnight, often around 2 a.m. They scan for sessions that need a person, open one,
  understand what the agent did and why, and step in. Finding a session and intervening must be easy.
- **Hackathon jury (secondary).** START Hack Munich 2026, 5U AI challenge. They see the screen live on
  a projector and in screenshots during a 3-minute pitch, and rate pitch, UX & design, codebase, and
  how human the agent's emails read.

## Product Purpose

"Leylü Forwarder" answers air-export requests for quote (RFQs) by email without a person. Every ~6
minutes a customer mails an RFQ; the agent reads it, extracts route, pieces, weights, cheapest vs
fastest and optional door pickup, prices it from airline rate sheets, a rate portal and 2–5 carrier
bids, and replies in the same mail thread with ONE all-in price within ~2 minutes. On acceptance it
books by rate ID, sends status updates, and answers tracking questions from its own CRM.

The Sessions UI is where the supervisor watches that system. One session = one customer request =
its CRM record.

Success per quote is scored on: price accuracy (within 5% of best price), LLM cost (near $0 is best,
$0.10 scores zero), and response time (full points ≤ 2:00, zero at 6:00).

## Positioning

The agent replies in the customer's own thread, in their language, with one all-in number, in under
two minutes, for a fraction of a cent of LLM cost. The UI makes that speed, cost and price choice
legible per session, and surfaces the few sessions where a person must act.

## Operating Context

- Overnight supervision on a laptop; projector and screenshots during the pitch. Desktop first; must
  not break on smaller widths.
- Data: sessions (CRM records), mail threads (customer mails vs our replies), agent event timeline
  (mail_in, routed, extracted, priced, carrier_asked, bid, quote_sent, accepted, booked, status_sent,
  tracking_answer, tariff_ingested, needs_human, intervened, error) with per-step LLM cost.
- Data source is either the live backend or bundled mock data; the header must say which.

## Capabilities and Constraints

- Next.js 15 App Router, TypeScript, Tailwind CSS 4, shadcn/ui, pnpm.
- `lib/types.ts` is a team contract (mirrors docs/CONTRACT.md) and must not change. `lib/api.ts`
  fetches with automatic mock fallback.
- Built now: session list with search (customer, route, reference, #id, carrier, booking ref) and
  stage filters, a "needs a person" queue and count; session detail with stage, outcome,
  paused/needs-a-person state, response time vs 2-min target, quoted all-in price, LLM cost, mail
  thread, event timeline, extracted request, price options with the quoted one marked, quote
  breakdown, booking and status updates.
- Coming next (not built; layout must leave room): live streaming of new steps, intervene controls
  (pause/resume, edit and send a reply by hand), CRM dashboard (won/lost, average response time, cost
  per accepted quote).
- Hackathon rule: only work written during the event counts.

## Brand Commitments

- Name: "Leylü" (team name), product "Leylü Forwarder". No logo asset exists.

## Evidence on Hand

- All session and mail content in `lib/mock.ts` is invented sample data. No real customers,
  carriers' real rates, or benchmarks exist; do not present any as real.

## Product Principles

1. The person is the exception path: make "needs a person" impossible to miss and one click away.
2. Show the score the agent is judged on (time, cost, price) where the decision is made, not in a
   separate report.
3. The mail thread is the truth the customer sees; keep it readable as mail.
4. Every agent step is accountable: what happened, when, and what it cost.
