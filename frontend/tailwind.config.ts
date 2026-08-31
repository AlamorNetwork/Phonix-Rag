import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Deep blue-slate, not pure black. Neutrals carry a cool bias toward the accent so
        // they read as chosen rather than inherited, and surfaces stack in real steps so the
        // interface has depth instead of being one flat sheet of grey boxes.
        base: {
          void: "#080b11",
          black: "#0b0f16",
          near: "#10151e",
          graphite: "#161d28",
          dark: "#1c2532",
          border: "#222c3a",
          borderStrong: "#31404f",
        },
        // Two accents that mean different things: teal is the system working, iris is a human
        // decision. A single lone accent is what made the old palette read as generic.
        accent: {
          emerald: "#0e7c63",
          emeraldBright: "#22c99f",
          iris: "#7c74e8",
          irisBright: "#9d95ff",
        },
        status: {
          success: "#3fb984",
          warning: "#e0a33c",
          critical: "#e2606b",
          info: "#68a3c9",
        },
        role: {
          manager: "#e0a33c",
          architect: "#9d95ff",
          coder: "#22c99f",
          reviewer: "#68a3c9",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        display: ["2.75rem", { lineHeight: "1", letterSpacing: "-0.02em" }],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 12px 32px -18px rgba(0,0,0,0.9)",
        glow: "0 0 0 1px rgba(34,201,159,0.25), 0 0 28px -6px rgba(34,201,159,0.35)",
      },
      backgroundImage: {
        "panel-sheen": "linear-gradient(160deg, rgba(255,255,255,0.035), transparent 45%)",
      },
    },
  },
  plugins: [],
};

export default config;
