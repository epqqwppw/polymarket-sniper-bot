/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: {
        brand: {
          dark: "#0f172a",
          card: "#1e293b",
          border: "#334155",
          accent: "#3b82f6",
        },
      },
    },
  },
  plugins: [],
};
