import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          black: "#08090b",
          near: "#0d0f12",
          graphite: "#15181c",
          dark: "#1c2026",
          border: "#262b32",
        },
        accent: {
          emerald: "#0f5c46",
          emeraldBright: "#17a877",
        },
        status: {
          success: "#4c9a6a",
          warning: "#c9982f",
          critical: "#c04747",
          info: "#5b7a92",
        },
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
