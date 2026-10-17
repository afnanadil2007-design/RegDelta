import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// The dev and preview servers proxy /api to the FastAPI backend, so the
// frontend uses one origin and the same relative base as the container build
// (VITE_API_BASE=/api, served by nginx there). The target follows the repo-root
// .env under the process environment, the same order the API's own settings
// use, so `make dev-web` reaches the API that `make dev-api` started:
// REGDELTA_API_URL if set, else 127.0.0.1:API_PORT. REGDELTA_WEB_PORT moves the
// dev server. Test configuration lives in vitest.config.ts.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, ".."), "");
  const api = env.REGDELTA_API_URL || `http://127.0.0.1:${env.API_PORT || 8000}`;
  const proxy = { "/api": { target: api, changeOrigin: true } };
  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
      host: "127.0.0.1",
      port: Number(env.REGDELTA_WEB_PORT || 5173),
      strictPort: true,
      proxy,
    },
    preview: {
      host: "127.0.0.1",
      port: Number(env.REGDELTA_WEB_PORT || 4173),
      strictPort: true,
      proxy,
    },
  };
});
