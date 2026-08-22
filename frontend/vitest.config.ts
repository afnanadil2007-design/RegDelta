import { defineConfig, mergeConfig } from "vitest/config";

import viteConfig from "./vite.config";

// Extends the Vite config with the test runner settings. Loaded by Vitest at
// runtime (esbuild), so it is intentionally outside the tsc build graph.
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: "./src/test-setup.ts",
      // e2e/ holds Playwright specs, which import @playwright/test and are run
      // by `npm run e2e`. Vitest must not try to collect them.
      include: ["src/**/*.{test,spec}.{ts,tsx}"],
    },
  }),
);
