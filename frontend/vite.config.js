import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Pre-transform the entry so the first page load finds everything ready.
    warmup: { clientFiles: ["./src/main.jsx", "./src/App.jsx"] },
  },
  // Pre-bundle React up front. Without this Vite discovers it during the first
  // page load and re-optimizes mid-load, and a browser that opened too early
  // gets a mix of old and new bundles: a blank page until a hard refresh.
  optimizeDeps: {
    include: ["react", "react-dom", "react-dom/client", "react/jsx-runtime", "react/jsx-dev-runtime"],
  },
});
