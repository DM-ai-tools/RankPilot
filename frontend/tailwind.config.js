/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        /* Professional SERPMapper-inspired palette */
        navy: { DEFAULT: "#0F2343", mid: "#2E4F7F" },
        brand: { DEFAULT: "#72C219", hover: "#5FA814" },
        teal: { DEFAULT: "#2E8B7F" },
        rp: {
          light: "#F3F8E9",
          shell: "#EDF4DD",
          border: "#DDE8CC",
          tmid: "#4D6078",
          tlight: "#8092A7",
          navmuted: "#70839D",
        },
      },
      fontFamily: {
        sans: ["Nunito Sans", "Poppins", "Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 8px 24px rgba(15,35,67,0.08)",
        app: "0 16px 48px rgba(15,35,67,0.15)",
      },
      borderRadius: {
        card: "14px",
      },
    },
  },
  plugins: [],
};
