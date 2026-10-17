/** @type {import('tailwindcss').Config} */
// Tokens mirror DESIGN.md. Colours are CSS variables (src/index.css) so the
// single light theme is defined in one place.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    // Fixed rem steps, ratio about 1.2; nothing below 12px.
    fontSize: {
      xs: ["0.75rem", { lineHeight: "1.4" }],
      sm: ["0.8125rem", { lineHeight: "1.4" }],
      base: ["0.875rem", { lineHeight: "1.45" }],
      md: ["1rem", { lineHeight: "1.45" }],
      doc: ["1.0625rem", { lineHeight: "1.6" }],
      lg: ["1.125rem", { lineHeight: "1.3" }],
      xl: ["1.375rem", { lineHeight: "1.25" }],
      "2xl": ["1.625rem", { lineHeight: "1.2" }],
      "3xl": ["2rem", { lineHeight: "1.15" }],
    },
    extend: {
      // The assessment workspace puts both leaves side by side from here.
      screens: { wide: "1440px" },
      colors: {
        desk: "var(--desk)",
        paper: "var(--paper)",
        raised: "var(--paper-raised)",
        ink: { DEFAULT: "var(--ink)", soft: "var(--ink-soft)", faint: "var(--ink-faint)" },
        rule: "var(--rule)",
        highlight: "var(--highlight)",
        focus: "var(--focus)",
        error: { DEFAULT: "var(--error)", tint: "var(--error-tint)" },
        impact: {
          conflict: "var(--conflict)",
          "conflict-tint": "var(--conflict-tint)",
          modified: "var(--modified)",
          "modified-tint": "var(--modified-tint)",
          new: "var(--new)",
          "new-tint": "var(--new-tint)",
          covered: "var(--covered)",
          "covered-tint": "var(--covered-tint)",
          none: "var(--none)",
          "none-tint": "var(--none-tint)",
        },
      },
      fontFamily: {
        sans: ['"Public Sans Variable"', "system-ui", "sans-serif"],
        serif: ['"Charis SIL"', "Georgia", "serif"],
      },
      borderRadius: { control: "3px" },
      maxWidth: { measure: "62ch" },
      boxShadow: { float: "0 8px 24px rgb(28 34 48 / 0.16)" },
    },
  },
  plugins: [],
};
