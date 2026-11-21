// The one place the UI talks to the backend. /api/* is proxied to BACKEND_URL (next.config.ts).
// If the backend is not reachable, the UI falls back to mock data so the demo never breaks.
import { mockEvents, mockSessions } from "./mock";
import type { Event, Session } from "./types";

export type Data = { sessions: Session[]; events: Event[]; live: boolean };

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

// F3: a person steps in. The agent checks `paused` before every send and sends queued manual replies.
export async function intervene(sessionId: number, action: "pause" | "resume" | "send", body?: string): Promise<void> {
  const res = await fetch(`/api/sessions/${sessionId}/intervene`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body === undefined ? { action } : { action, body }),
  });
  if (!res.ok) throw new Error(`intervene ${action}: ${res.status}`);
}

export async function loadData(): Promise<Data> {
  try {
    const sessions = await getJson<Session[]>("/api/sessions");
    // Event history per session: GET /api/sessions/{id}/events is a proposal, not in the contract yet.
    const events = (
      await Promise.all(sessions.map((s) => getJson<Event[]>(`/api/sessions/${s.id}/events`).catch(() => [])))
    ).flat();
    return { sessions, events, live: true };
  } catch {
    return { sessions: mockSessions, events: mockEvents, live: false };
  }
}
