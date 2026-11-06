import { defineConfig } from "vitest/config";

// Served from GitHub Pages at /rainsure/, next to the published data in /rainsure/data/ (DECISIONS.md D52).
export default defineConfig({
  base: "/rainsure/",
  build: { target: "es2022", sourcemap: false },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
