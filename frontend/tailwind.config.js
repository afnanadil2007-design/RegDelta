/** @type {import('tailwindcss').Config} */
// Restrained palette for a professional internal tool. No dark mode by design.
// Colours are driven by CSS variables (see src/index.css) so shadcn/ui
// primitives can be dropped in without rewiring.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        // Impact-type semantic colours (used by FindingsTable in Stage 10).
        impact: {
          new: "hsl(var(--impact-new))",
          modified: "hsl(var(--impact-modified))",
          conflict: "hsl(var(--impact-conflict))",
          covered: "hsl(var(--impact-covered))",
          none: "hsl(var(--impact-none))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};
