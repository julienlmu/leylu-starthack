"use client";
// Command UI prototype shell: one live-data subscription for every /command page, the sidebar, the top bar, the theme.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useLiveData, type LiveData } from "@/lib/live";
import { group } from "@/lib/command/derive";

const Ctx = createContext<LiveData | null>(null);
export const useCommand = () => useContext(Ctx);

const KEY = "cmd-theme";

// Ticks once a second, for running clocks.
export function useNow() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

// Title + one-line explanation per page (the spec's PAGES map).
const PAGES: Record<string, [string, string]> = {
  "/command": ["Requests", "New price questions from customers"],
  "/command/quotes": ["Sent quotes", "Prices we sent, waiting for the customer's answer"],
  "/command/bookings": ["Bookings", "Shipments booked with the airline"],
  "/command/tracking": ["Shipment tracking", "Customers asking where their shipment is"],
  "/command/prices": ["Prices & airlines", "Where the assistant gets its prices"],
  "/command/settings": ["Settings", "How the assistant behaves"],
};

type Tab = { href: string; icon: ReactNode; count?: (d: LiveData) => number; hot?: boolean };
const NAV: { group: string; tabs: Tab[] }[] = [
  { group: "Work", tabs: [
    { href: "/command", hot: true, count: (d) => d.sessions.filter((s) => group(s) === "need").length,
      icon: <><path d="M2 4h12v8H2z" /><path d="m2 4 6 4.5L14 4" /></> },
    { href: "/command/quotes", count: (d) => d.sessions.filter((s) => s.quote && !s.booking && s.outcome === "open").length,
      icon: <><path d="M3.5 2h6.5L12.5 4.5V14h-9z" /><path d="M5.5 7.5h5M5.5 10h3.5" /></> },
    { href: "/command/bookings", count: (d) => d.sessions.filter((s) => s.booking).length,
      icon: <><path d="M3 6.5h10V14H3z" /><path d="M5.5 6.5V4.5a2.5 2.5 0 0 1 5 0v2" /></> },
    { href: "/command/tracking",
      icon: <><path d="M8 14s4.5-4.2 4.5-7.5a4.5 4.5 0 0 0-9 0C3.5 9.8 8 14 8 14z" /><circle cx="8" cy="6.5" r="1.6" /></> },
  ] },
  { group: "Setup", tabs: [
    { href: "/command/prices", icon: <path d="M2.5 12.5 6 8l3 2.5 4.5-6" /> },
    { href: "/command/settings", icon: <><circle cx="8" cy="8" r="2" /><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" /></> },
  ] },
];

const isDark = (root: Element) => {
  const t = root.getAttribute("data-theme");
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
};

export function Shell({ children }: { children: ReactNode }) {
  const data = useLiveData();
  const path = usePathname();
  const [title, sub] = PAGES[path] ?? PAGES["/command"];
  // The layout's inline script applied the stored theme before paint; mirror it for the button label.
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const root = document.querySelector(".cmd");
    if (root) setDark(isDark(root));
  }, []);
  const toggle = () => {
    const root = document.querySelector(".cmd");
    if (!root) return;
    const next = isDark(root) ? "light" : "dark";
    root.setAttribute("data-theme", next);
    setDark(next === "dark");
    try {
      localStorage.setItem(KEY, next);
    } catch {}
  };

  const needs = data?.sessions.filter((s) => group(s) === "need").length ?? 0;
  const on = !!data?.live && data.connected;
  const state = !data ? "Connecting" : !data.live ? "Sample data" : data.connected ? "Assistant on" : "Reconnecting";
  const note = !data
    ? "Connecting to the assistant."
    : !data.live
      ? "Backend not reachable: showing the built-in sample night. Nothing can be sent."
      : needs
        ? `Answers every request on its own. ${needs} red one${needs === 1 ? "" : "s"} need${needs === 1 ? "s" : ""} you.`
        : "Answers every request on its own. Red ones need you.";

  return (
    <Ctx.Provider value={data}>
      <div className="app">
        <aside className="side">
            <Link className="brand" href="/command">
              <svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><circle cx="16" cy="16" r="13" stroke="var(--text)" strokeWidth="1.7" /><ellipse cx="16" cy="16" rx="5.6" ry="13" stroke="var(--text)" strokeWidth="1.2" opacity=".55" /><path d="M3.6 12h24.8M3.6 20h24.8" stroke="var(--text)" strokeWidth="1.2" opacity=".55" /><path d="M8 21.5C11.5 10.5 20.5 9 25.5 11.5" stroke="var(--accent)" strokeWidth="2.1" strokeLinecap="round" /><circle cx="25.5" cy="11.5" r="2.3" fill="var(--accent)" /></svg>
              Leylü
            </Link>
            {NAV.map((g) => (
              <nav key={g.group} className="navg" aria-label={g.group}>
                <h4>{g.group}</h4>
                {g.tabs.map((t) => {
                  const n = data && t.count ? t.count(data) : 0;
                  return (
                    <Link key={t.href} href={t.href} aria-current={path === t.href ? "page" : undefined}>
                      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">{t.icon}</svg>
                      {PAGES[t.href][0]}
                      {n > 0 && <span className={`count${t.hot ? " hot" : ""}`}>{n}<span className="sr">{t.hot ? " need you" : ""}</span></span>}
                    </Link>
                  );
                })}
              </nav>
            ))}
            <div className={`agent${on ? "" : " paused"}`}>
              <div className="row">
                <span className="live"><i aria-hidden="true" />{state}</span>
                <span title="There is no endpoint to pause the whole assistant. Hold a single request from its detail panel instead.">
                  <button className="btn" type="button" disabled>Pause</button>
                </span>
              </div>
              <small>{note}</small>
            </div>
        </aside>
        <main className="main">
          <div className="top">
            <h1>{title}</h1>
            <span className="sub">{sub}</span>
            {data && !data.live && <span className="sample" title="The backend is not reachable; this is the built-in sample night.">Sample data</span>}
            <div className="sp">
              <button className="btn" type="button" onClick={toggle}>{dark ? "Light mode" : "Dark mode"}</button>
            </div>
          </div>
          {children}
        </main>
      </div>
    </Ctx.Provider>
  );
}
