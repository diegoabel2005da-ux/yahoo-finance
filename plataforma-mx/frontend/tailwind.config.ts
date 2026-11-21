import type { Config } from "tailwindcss";
export default {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { DEFAULT: "#0B1F3A", 50: "#EEF2F8", 100: "#D6DFEC", 700: "#132C52", 800: "#0E2444", 900: "#0B1F3A", 950: "#07152A" },
        turq: { DEFAULT: "#14B8A6", 600: "#0D9488", 700: "#0F766E" },
      },
      fontFamily: { mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"] },
    },
  },
} satisfies Config;
