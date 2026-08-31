import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          black: "#07080a",
          near: "#0c0e11",
          graphite: "#12151a",
          dark: "#171b21",
          border: "#1f242b",
          borderStrong: "#2b323b",
        },
        accent: {
          emerald: "#0d5c44",
          emeraldBright: "#18b47f",
        },
        // Semantic state, kept separate from the accent hue so "it worked" never reads as
        // "this is the brand colour".
        status: {
          success: "#4fa87a",
          warning: "#d0a03a",
          critical: "#d05a5a",
          info: "#6f8ea6",
        },
        // One hue per agent role, so a role is recognisable at a glance across every screen.
        role: {
          manager: "#c9922f",
          architect: "#9b7fd4",
          coder: "#18b47f",
          reviewer: "#5b9dd9",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.8)",
      },
    },
  },
  plugins: [],
};

export default config;
