import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import svgr from 'vite-plugin-svgr'
import cesium from "vite-plugin-cesium";

export default defineConfig({
  plugins: [react(), svgr(), cesium()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          if (id.includes("cesium") || id.includes("resium")) return "vendor-cesium";
          if (id.includes("three") || id.includes("@react-three")) return "vendor-3d";
          if (id.includes("maplibre") || id.includes("leaflet")) return "vendor-maps";
          if (id.includes("@mui") || id.includes("@emotion")) return "vendor-mui";
          if (id.includes("@react-google-maps") || id.includes("@googlemaps")) {
            return "vendor-google-maps";
          }
          return "vendor";
        },
      },
    },
  },
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
      "/fields": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/geofences": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/mapping": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/mapping-assets": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/telemetry": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/runtime": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/warehouse": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
      "/video-analysis": {
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
