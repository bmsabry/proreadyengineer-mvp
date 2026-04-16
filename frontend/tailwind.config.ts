
import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      // ── BRAND COLOR TOKENS ─────────────────────────────────────────────
      colors: {
        // shadcn/ui CSS-variable driven tokens (keep as-is)
        border:     "hsl(var(--border))",
        input:      "hsl(var(--input))",
        ring:       "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT:    "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT:    "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT:    "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT:    "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT:    "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT:    "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT:    "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },

        // ── ProReadyEngineer direct brand palette ──────────────────────
        navy: {
          50:  "#eef3fb",
          100: "#d5e2f5",
          200: "#abc5eb",
          300: "#7fa3de",
          400: "#5482d0",
          500: "#3162be",
          600: "#254ea0",
          700: "#1c3c7e",
          800: "#152d61",
          900: "#0f2044",
          950: "#0F2B54",   // brand primary
        },
        steel: {
          50:  "#f4f6f9",
          100: "#e8ecf2",
          200: "#cdd6e4",
          300: "#adbace",
          400: "#8799b5",
          500: "#697d9e",
          600: "#526384",
          700: "#42506b",
          800: "#384459",
          900: "#303b4c",
          950: "#1e2737",
        },
        electric: {
          50:  "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",   // accent primary
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
          950: "#172554",
        },
      },

      // ── TYPOGRAPHY ─────────────────────────────────────────────────────
      fontFamily: {
        sans:  ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono:  ["JetBrains Mono", "Fira Code", "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "0.875rem" }],
        xs:    ["0.75rem",  { lineHeight: "1rem" }],
        sm:    ["0.875rem", { lineHeight: "1.25rem" }],
        base:  ["1rem",     { lineHeight: "1.6rem" }],
        lg:    ["1.125rem", { lineHeight: "1.75rem" }],
        xl:    ["1.25rem",  { lineHeight: "1.875rem" }],
        "2xl": ["1.5rem",   { lineHeight: "2rem" }],
        "3xl": ["1.875rem", { lineHeight: "2.25rem" }],
        "4xl": ["2.25rem",  { lineHeight: "2.5rem",  letterSpacing: "-0.02em" }],
        "5xl": ["3rem",     { lineHeight: "1",        letterSpacing: "-0.025em" }],
        "6xl": ["3.75rem",  { lineHeight: "1",        letterSpacing: "-0.03em" }],
      },
      letterSpacing: {
        tighter: "-0.03em",
        tight:   "-0.02em",
        snug:    "-0.01em",
        normal:  "0em",
        wide:    "0.02em",
        wider:   "0.04em",
        widest:  "0.08em",
      },
      lineHeight: {
        tightest: "1.1",
        tighter:  "1.2",
        tight:    "1.35",
        snug:     "1.45",
        normal:   "1.6",
        relaxed:  "1.75",
        loose:    "2",
      },

      // ── BORDER RADIUS ──────────────────────────────────────────────────
      borderRadius: {
        none: "0",
        xs:   "2px",
        sm:   "calc(var(--radius) - 4px)",
        md:   "calc(var(--radius) - 2px)",
        DEFAULT: "var(--radius)",
        lg:   "var(--radius)",
        xl:   "calc(var(--radius) + 4px)",
        "2xl": "calc(var(--radius) + 8px)",
        "3xl": "1.5rem",
        full: "9999px",
      },

      // ── SHADOWS ────────────────────────────────────────────────────────
      boxShadow: {
        // Subtle card elevation system using navy brand color
        xs:    "0 1px 2px 0 rgb(15 43 84 / 0.05)",
        sm:    "0 1px 3px 0 rgb(15 43 84 / 0.08), 0 1px 2px -1px rgb(15 43 84 / 0.05)",
        DEFAULT: "0 2px 6px 0 rgb(15 43 84 / 0.10), 0 1px 3px -1px rgb(15 43 84 / 0.06)",
        md:    "0 4px 12px 0 rgb(15 43 84 / 0.10), 0 2px 6px -2px rgb(15 43 84 / 0.06)",
        lg:    "0 8px 24px 0 rgb(15 43 84 / 0.12), 0 4px 12px -4px rgb(15 43 84 / 0.08)",
        xl:    "0 16px 40px 0 rgb(15 43 84 / 0.14), 0 8px 20px -6px rgb(15 43 84 / 0.10)",
        "2xl": "0 24px 64px 0 rgb(15 43 84 / 0.18), 0 12px 28px -8px rgb(15 43 84 / 0.12)",
        // Accent glow variants
        "accent-sm": "0 0 0 3px hsl(217 91% 60% / 0.12)",
        "accent-md": "0 0 0 4px hsl(217 91% 60% / 0.16), 0 4px 16px 0 hsl(217 91% 60% / 0.12)",
        // Pricing featured card
        featured: "0 0 0 1px hsl(217 91% 60% / 0.2), 0 8px 32px 0 rgb(59 130 246 / 0.12)",
        // Inner
        inner: "inset 0 1px 4px 0 rgb(15 43 84 / 0.06)",
        none:  "none",
      },
      // ── SPACING / SIZING ───────────────────────────────────────────────
      spacing: {
        "4.5":  "1.125rem",
        "5.5":  "1.375rem",
        "6.5":  "1.625rem",
        "7.5":  "1.875rem",
        "13":   "3.25rem",
        "15":   "3.75rem",
        "18":   "4.5rem",
        "22":   "5.5rem",
        "26":   "6.5rem",
        "30":   "7.5rem",
        "34":   "8.5rem",
        "128":  "32rem",
        "144":  "36rem",
      },
      maxWidth: {
        "2xs":  "16rem",
        xs:     "20rem",
        sm:     "24rem",
        md:     "28rem",
        lg:     "32rem",
        xl:     "36rem",
        "2xl":  "42rem",
        "3xl":  "48rem",
        "4xl":  "56rem",
        "5xl":  "64rem",
        "6xl":  "72rem",
        "7xl":  "80rem",
        narrow: "42rem",
        default: "68rem",
        wide:   "88rem",
        full:   "100%",
      },

      // ── KEYFRAMES & ANIMATIONS ─────────────────────────────────────────
      keyframes: {
        // Radix UI accordion
        "accordion-down": {
          from: { height: "0" },
          to:   { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to:   { height: "0" },
        },
        // Fade
        "fade-in": {
          from: { opacity: "0" },
          to:   { opacity: "1" },
        },
        "fade-out": {
          from: { opacity: "1" },
          to:   { opacity: "0" },
        },
        // Slide
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "slide-down": {
          from: { opacity: "0", transform: "translateY(-8px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-left": {
          from: { opacity: "0", transform: "translateX(-8px)" },
          to:   { opacity: "1", transform: "translateX(0)" },
        },
        "slide-in-right": {
          from: { opacity: "0", transform: "translateX(8px)" },
          to:   { opacity: "1", transform: "translateX(0)" },
        },
        // Scale
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.95)" },
          to:   { opacity: "1", transform: "scale(1)" },
        },
        "scale-out": {
          from: { opacity: "1", transform: "scale(1)" },
          to:   { opacity: "0", transform: "scale(0.95)" },
        },
        // Spin / loader
        spin: {
          from: { transform: "rotate(0deg)" },
          to:   { transform: "rotate(360deg)" },
        },
        // Pulse glow
        "pulse-glow": {
          "0%, 100%": { boxShadow: "0 0 0 0 hsl(217 91% 60% / 0)" },
          "50%":      { boxShadow: "0 0 0 6px hsl(217 91% 60% / 0.15)" },
        },
        // Shimmer skeleton
        shimmer: {
          "0%":   { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        // Bounce subtle
        "bounce-sm": {
          "0%, 100%": { transform: "translateY(0)" },
          "50%":      { transform: "translateY(-4px)" },
        },
      },
      animation: {
        "accordion-down":  "accordion-down 0.2s ease-out",
        "accordion-up":    "accordion-up 0.2s ease-out",
        "fade-in":         "fade-in 0.15s ease-out",
        "fade-out":        "fade-out 0.15s ease-in",
        "slide-up":        "slide-up 0.2s ease-out",
        "slide-down":      "slide-down 0.2s ease-out",
        "slide-in-left":   "slide-in-left 0.2s ease-out",
        "slide-in-right":  "slide-in-right 0.2s ease-out",
        "scale-in":        "scale-in 0.15s ease-out",
        "scale-out":       "scale-out 0.15s ease-in",
        spin:              "spin 1s linear infinite",
        "pulse-glow":      "pulse-glow 2s ease-in-out infinite",
        shimmer:           "shimmer 1.5s linear infinite",
        "bounce-sm":       "bounce-sm 1s ease-in-out infinite",
      },

      // ── TRANSITIONS ────────────────────────────────────────────────────
      transitionDuration: {
        "0":   "0ms",
        "75":  "75ms",
        "100": "100ms",
        "150": "150ms",
        "200": "200ms",
        "300": "300ms",
        "500": "500ms",
        "700": "700ms",
        "1000": "1000ms",
      },
      transitionTimingFunction: {
        DEFAULT:  "cubic-bezier(0.4, 0, 0.2, 1)",
        linear:   "linear",
        in:       "cubic-bezier(0.4, 0, 1, 1)",
        out:      "cubic-bezier(0, 0, 0.2, 1)",
        "in-out": "cubic-bezier(0.4, 0, 0.2, 1)",
        bounce:   "cubic-bezier(0.34, 1.56, 0.64, 1)",
        spring:   "cubic-bezier(0.175, 0.885, 0.32, 1.275)",
      },

      // ── Z-INDEX ────────────────────────────────────────────────────────
      zIndex: {
        "0":    "0",
        "10":   "10",
        "20":   "20",
        "30":   "30",
        "40":   "40",
        "50":   "50",
        dropdown: "1000",
        sticky:   "1020",
        fixed:    "1030",
        modal:    "1040",
        popover:  "1050",
        tooltip:  "1060",
        toast:    "1070",
      },

      // ── ASPECT RATIOS ──────────────────────────────────────────────────
      aspectRatio: {
        auto:    "auto",
        square:  "1 / 1",
        video:   "16 / 9",
        "4/3":   "4 / 3",
        "3/2":   "3 / 2",
        "2/1":   "2 / 1",
        "golden": "1.618 / 1",
      },

      // ── BACKDROP BLUR ──────────────────────────────────────────────────
      backdropBlur: {
        none: "0",
        xs:   "2px",
        sm:   "4px",
        DEFAULT: "8px",
        md:   "12px",
        lg:   "16px",
        xl:   "24px",
        "2xl": "40px",
        "3xl": "64px",
      },
    },
  },
  plugins: [
    require("tailwindcss-animate"),
  ],
}

export default config
