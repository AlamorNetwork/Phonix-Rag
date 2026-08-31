import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

// A technical, engineering-desk pairing rather than the default UI grotesque: Plex reads as
// instrumentation, which is what this is, and the mono is the same family so numbers and
// identifiers sit naturally beside prose.
const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Phoenix Forge",
  description: "AI Engineering & Infrastructure Command Center",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="bg-base-black text-neutral-200 font-sans antialiased">{children}</body>
    </html>
  );
}
