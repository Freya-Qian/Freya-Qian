import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1f2433",
        graphite: "#626b80",
        line: "#e6e9f2",
        panel: "#f6f7fc",
        station: "#3c58d7",
        blueprint: "#4d6bfe",
        amberline: "#b7791f",
      },
      boxShadow: {
        rail: "0 18px 60px rgba(24, 33, 47, 0.10)",
      },
    },
  },
  plugins: [],
};

export default config;
