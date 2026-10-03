import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development the browser talks to Vite (5173) and Vite proxies API calls to FastAPI (8000),
// so no CORS is involved. Production: serve the built files and the API behind one reverse proxy.
const backend = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": backend, "/health": backend },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.js",
    css: false,
  },
});
