// Command UI prototype at /command: a separate route with its own look; the live UI at / is untouched.
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Shell } from "@/components/command/shell";
import "./command.css";

const geist = Geist({ variable: "--font-geist", subsets: ["latin", "latin-ext"], weight: ["400", "500", "600"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "Command · Leylü Forwarder (prototype)",
  description: "Prototype operator console for the Leylü AI air forwarder.",
};

// Applies the stored theme before first paint (no flash). Default: follow the system.
const THEME = `try{var v=localStorage.getItem("cmd-theme");if(v==="light"||v==="dark")document.currentScript.parentElement.setAttribute("data-theme",v)}catch(e){}`;

export default function CommandLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={`cmd ${geist.variable} ${geistMono.variable}`} suppressHydrationWarning>
      <script dangerouslySetInnerHTML={{ __html: THEME }} />
      <Shell>{children}</Shell>
    </div>
  );
}
