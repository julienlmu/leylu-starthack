"use client";
// Small pieces shared by the Sent quotes, Bookings, Tracking and Prices pages.
import { useEffect, useState } from "react";
import type { LiveData } from "@/lib/live";
import { Drawer } from "./requests";

export function Search({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="search">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></svg>
      <input type="search" value={value} onChange={(e) => onChange(e.target.value)} placeholder="Search" aria-label={label} />
    </label>
  );
}

// The home's request drawer, opened from any page: pick(id) opens it, the element renders it.
export function useDrawer(data: LiveData | null, now: number) {
  const [id, setId] = useState<number | null>(null);
  const loadEvents = data?.loadEvents;
  useEffect(() => {
    if (id && loadEvents) loadEvents(id);
  }, [id, loadEvents]);
  const s = data?.sessions.find((x) => x.id === id);
  return { pick: setId, drawer: data && s ? <Drawer s={s} data={data} now={now} onClose={() => setId(null)} /> : null };
}

// Live mode loads event history per session on demand; these pages need it for every listed session.
export function useEvents(data: LiveData | null, ids: number[]) {
  const loadEvents = data?.loadEvents;
  const key = ids.join(",");
  useEffect(() => {
    if (loadEvents && key) key.split(",").forEach((x) => loadEvents(Number(x)));
  }, [key, loadEvents]);
}
