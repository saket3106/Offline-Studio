import { defineConfig } from "vitest/config";
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/**/*.vitest.{js,jsx}"],
    maxWorkers: 1,
    pool: "threads",
    testTimeout: 5000,
    hookTimeout: 5000,
    fileParallelism: false,
    setupFiles: ["./src/testSetup.js"],
  },
  esbuild: { jsx: "automatic" },
});
