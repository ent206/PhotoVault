/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // All colors use CSS variables so both themes work automatically.
        // Opacity modifiers (bg-amber/20, border-danger/30, etc.) work via
        // the rgb() / <alpha-value> pattern.
        bg:          "rgb(var(--rgb-bg) / <alpha-value>)",
        surface:     "rgb(var(--rgb-surface) / <alpha-value>)",
        card:        "rgb(var(--rgb-card) / <alpha-value>)",
        "card-hi":   "rgb(var(--rgb-card-hi) / <alpha-value>)",
        border:      "rgb(var(--rgb-border) / <alpha-value>)",
        "border-hi": "rgb(var(--rgb-border-hi) / <alpha-value>)",
        text:        "rgb(var(--rgb-text) / <alpha-value>)",
        muted:       "rgb(var(--rgb-muted) / <alpha-value>)",
        "muted-hi":  "rgb(var(--rgb-muted-hi) / <alpha-value>)",
        amber:       "rgb(var(--rgb-amber) / <alpha-value>)",
        "amber-dim": "rgb(var(--rgb-amber-dim) / <alpha-value>)",
        "amber-glow":"rgba(212,146,74,0.15)",
        success:     "rgb(var(--rgb-success) / <alpha-value>)",
        danger:      "rgb(var(--rgb-danger) / <alpha-value>)",
        "danger-hover": "rgb(168 45 45 / <alpha-value>)",
        warn:        "rgb(var(--rgb-warn) / <alpha-value>)",
        "surface-hover": "rgb(var(--rgb-card) / <alpha-value>)",
      },
      fontFamily: {
        display: ['"Cormorant Garamond"', "Georgia", "serif"],
        sans:    ['"DM Sans"', "system-ui", "sans-serif"],
        mono:    ['"JetBrains Mono"', "Menlo", "monospace"],
      },
      fontSize: {
        "display-xl": ["3.5rem", { lineHeight: "1.05", letterSpacing: "-0.02em" }],
        "display-lg": ["2.5rem", { lineHeight: "1.08", letterSpacing: "-0.02em" }],
        "display-md": ["1.75rem", { lineHeight: "1.1",  letterSpacing: "-0.01em" }],
      },
      boxShadow: {
        "amber-glow": "0 0 30px rgba(212,146,74,0.18), 0 0 60px rgba(212,146,74,0.08)",
        "amber-sm":   "0 0 12px rgba(212,146,74,0.25)",
        "card":       "var(--card-shadow)",
      },
      backgroundImage: {
        "amber-gradient":   "linear-gradient(135deg, #d4924a 0%, #b8763a 100%)",
        "surface-gradient": "var(--screen-gradient)",
      },
    },
  },
  plugins: [],
}
