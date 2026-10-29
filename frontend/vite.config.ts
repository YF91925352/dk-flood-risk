import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// In development the API runs on :8000; in Docker, nginx proxies /api and /health instead.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/health": "http://localhost:8000",
    },
  },
  test: { environment: "node" },
});
