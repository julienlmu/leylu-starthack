// The one place the UI talks to the backend. /api/* is proxied to BACKEND_URL (next.config.ts).
// If the backend is not reachable, the UI falls back to mock data so the demo never breaks.
import { mockEvents, mockSessions } from "./mock";
import type { Event, Session } from "./types";

export type Data = { sessions: Session[]; events: Event[]; live: boolean };

// The backend answered with an error (vs. not answering at all, which surfaces as a TypeError from fetch).
export class BackendError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`backend answered ${status}${detail ? `: ${detail}` : ""}`);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: "no-store", ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new BackendError(res.status, typeof body?.detail === "string" ? body.detail : "");
  }
  return res.json();
}

// Sessions only. Event history is loaded per session when it is needed (see loadEvents): there is no bulk
// endpoint, and one request per session on every page mount does not scale through the night.
export async function loadData(): Promise<Data> {
  try {
    return { sessions: await call<Session[]>("/api/sessions"), events: [], live: true };
  } catch {
    return { sessions: mockSessions, events: mockEvents, live: false };
  }
}

export const loadSession = (id: number) => call<Session>(`/api/sessions/${id}`);
export const loadEvents = (id: number) => call<Event[]>(`/api/sessions/${id}/events`);

// F3: a person steps in. Returns the session as the backend saved it.
export const intervene = (sessionId: number, action: "pause" | "resume" | "send", body?: string) =>
  call<Session>(`/api/sessions/${sessionId}/intervene`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body === undefined ? { action } : { action, body }),
  });
