import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // Must mirror `paths` in tsconfig.json; tsc alone only satisfies the type checker.
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    // The backend serves the capsule and its media. Proxying keeps the frontend
    // same-origin, so <img src="/media/..."> works without CORS or absolute URLs.
    proxy: {
      "/api": "http://127.0.0.1:8787",
      "/media": "http://127.0.0.1:8787",
      "/tracks": "http://127.0.0.1:8787",
    },
  },
});
