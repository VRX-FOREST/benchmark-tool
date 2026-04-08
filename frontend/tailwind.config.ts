import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"DM Sans"', "system-ui", "sans-serif"],
        display: ['"Syne"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "monospace"],
      },
      colors: {
        /* Bleu Nuit — PANTONE PQ-288C — couleur principale */
        brand: {
          50: "#e6ecf5",
          100: "#b3c4de",
          200: "#809cc7",
          300: "#4d74b0",
          400: "#264da0",
          500: "#002D72",  /* Bleu Nuit exact */
          600: "#002663",
          700: "#001F54",
          800: "#001845",
          900: "#001136",
          950: "#000a22",
        },
        /* Rouge — PANTONE 485 XGC — alertes et CTA */
        accent: {
          50: "#fde8e7",
          100: "#f9bcb8",
          200: "#f59089",
          300: "#f1645a",
          400: "#e8413a",
          500: "#DA291C",  /* Rouge exact */
          600: "#c02318",
          700: "#a01d14",
          800: "#801710",
          900: "#60110c",
        },
        /* Gris — basé sur Warm Gray Pantone */
        surface: {
          0: "#ffffff",     /* Blanc — fond principal */
          50: "#f7f6f4",    /* Blanc cassé chaud */
          100: "#edecea",   /* Gris très clair chaud */
          200: "#D7D2CB",   /* PANTONE Warm Gray 1 C — fonds de cartes */
          300: "#c4beb6",   /* Gris clair intermédiaire */
          400: "#B2A89F",   /* PANTONE Warm Gray 3 C — textes secondaires */
          500: "#978e84",   /* Gris moyen */
          600: "#7a7169",   /* Gris foncé */
          700: "#5c544e",   /* Texte secondaire fort */
          800: "#3e3833",   /* Texte quasi-noir */
          900: "#1e1b18",   /* Quasi-noir chaud */
        },
      },
    },
  },
  plugins: [],
};

export default config;
