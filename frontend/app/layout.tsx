import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Phoenix Forge",
  description: "AI Engineering & Infrastructure Command Center",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-base-black text-neutral-200 font-sans antialiased">{children}</body>
    </html>
  );
}
