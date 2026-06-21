/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
    "./components/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Light "Nexcent" palette — green accent on white/light-gray.
        primary: { DEFAULT: "#4CAF4F", dark: "#3d9140", light: "#7AC77B" },
        accent: { DEFAULT: "#4CAF4F", dark: "#3d9140" },
        ink: "#263238",        // headings / dark text
        body: "#717171",       // body copy
        canvas: "#FFFFFF",     // page background
        soft: "#F5F7FA",       // light gray section bands
        mint: "#E8F5E9",       // pale green chips / icon backdrops
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        soft: "0 8px 30px -12px rgba(38,50,56,0.12)",
        card: "0 12px 40px -16px rgba(38,50,56,0.18)",
        glow: "0 12px 30px -10px rgba(76,175,79,0.45)",
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
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.6s ease-out both",
        float: "float 6s ease-in-out infinite",
        marquee: "marquee 32s linear infinite",
      },
    },
  },
  plugins: [],
};
