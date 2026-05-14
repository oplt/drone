import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import svgr from 'vite-plugin-svgr'
import cesium from "vite-plugin-cesium";

export default defineConfig({
  plugins: [react(), svgr(), cesium()],
  server: {
    headers: {
      "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
      Pragma: "no-cache",
      Expires: "0",
    },
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/auth": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/tasks": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/telemetry": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/video": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/analytics": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
    },
  },
});
