/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#f0f4ff",
          100: "#dce6ff",
          200: "#b9cdff",
          300: "#84a8ff",
          400: "#4d7bff",
          500: "#2459ff",
          600: "#0d3af5",
          700: "#0a2de1",
          800: "#0f26b6",
          900: "#12238f",
          950: "#0d1657",
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      animation: {
        "fade-in":    "fadeIn 0.2s ease-out",
        "slide-up":   "slideUp 0.25s ease-out",
        "pulse-dot":  "pulseDot 1.4s ease-in-out infinite",
      },
      keyframes: {
        fadeIn:   { from: { opacity: 0 }, to: { opacity: 1 } },
        slideUp:  { from: { transform: "translateY(8px)", opacity: 0 }, to: { transform: "translateY(0)", opacity: 1 } },
        pulseDot: { "0%, 80%, 100%": { transform: "scale(0.6)", opacity: 0.4 }, "40%": { transform: "scale(1)", opacity: 1 } },
      },
    },
  },
  plugins: [],
};
