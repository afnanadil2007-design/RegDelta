import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to the FastAPI backend so the frontend uses a
// single origin and the same relative base as production (VITE_API_BASE=/api).
// REGDELTA_API_URL / REGDELTA_WEB_PORT let a machine whose 8000 or 5173 is
// taken run the stack elsewhere. Test configuration lives in vitest.config.ts.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    host: "127.0.0.1",
    port: Number(process.env.REGDELTA_WEB_PORT ?? 5173),
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.REGDELTA_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: Number(process.env.REGDELTA_WEB_PORT ?? 4173),
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.REGDELTA_API_URL ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
