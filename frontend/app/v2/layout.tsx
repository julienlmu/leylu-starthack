import type { Metadata } from "next";
import "./v2.css";

export const metadata: Metadata = {
  title: "Round · Leylü Forwarder (v2 proposal)",
  description: "Proposal: one screen that shows the current RFQ round, the sessions and the quote we sent.",
};

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return <div className="v2 min-h-screen">{children}</div>;
}
