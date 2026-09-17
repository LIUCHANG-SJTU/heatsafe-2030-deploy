import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
// The frontend tsconfig excludes Node typings; this import runs only in Vite's Node build process.
// @ts-expect-error build-time Node API
import { readFileSync } from "node:fs";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  return {
    plugins: [react(), {
      name: "maplibre-worker-shared-module",
      generateBundle() {
        this.emitFile({
          type: "asset",
          fileName: "assets/maplibre-gl-shared.mjs",
          source: readFileSync(new URL("./node_modules/maplibre-gl/dist/maplibre-gl-shared.mjs", import.meta.url)),
        });
      },
    }],
    server: {
      port: 5173,
      proxy: { "/api": env.VITE_DEV_API_PROXY_TARGET || "http://127.0.0.1:8000" },
    },
  };
});
