/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
    "./components/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Brand palette.
        primary: { DEFAULT: "#6366F1", dark: "#4338CA", light: "#818CF8" },
        accent: { DEFAULT: "#22D3EE", dark: "#06B6D4" },
        violet: { DEFAULT: "#A855F7", light: "#C084FC" },
        // Cinematic dark surfaces.
        ink: "#05060E",        // deepest background
        surface: "#0B0E1A",    // card / panel surface
        canvas: "#070912",     // page background
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 40px -8px rgba(99,102,241,0.55)",
        "glow-cyan": "0 0 40px -8px rgba(34,211,238,0.5)",
        card: "0 20px 60px -20px rgba(2,4,16,0.8)",
      },
      backgroundImage: {
        "radial-fade": "radial-gradient(ellipse at top, rgba(99,102,241,0.18), transparent 60%)",
        "aurora": "conic-gradient(from 180deg at 50% 50%, #6366F1, #22D3EE, #A855F7, #6366F1)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(16px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        float: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        "aurora-spin": {
          "0%": { transform: "rotate(0deg) scale(1.4)" },
          "100%": { transform: "rotate(360deg) scale(1.4)" },
        },
        "pulse-glow": {
          "0%,100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s ease-out both",
        float: "float 6s ease-in-out infinite",
        "aurora-spin": "aurora-spin 18s linear infinite",
        "pulse-glow": "pulse-glow 4s ease-in-out infinite",
        marquee: "marquee 32s linear infinite",
        shimmer: "shimmer 2.2s infinite",
      },
    },
  },
  plugins: [],
};
