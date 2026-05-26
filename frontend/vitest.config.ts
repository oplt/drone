import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    "import.meta.env.VITE_API_BASE_URL": JSON.stringify(""),
  },
  esbuild: {
    tsconfigRaw: {
      compilerOptions: {
        types: ["vitest/globals", "@testing-library/jest-dom"],
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: [
      "src/**/*.{test,spec}.{ts,tsx}",
      "scripts/**/*.test.mjs",
    ],
    globals: true,
    css: false,
  },
});
