import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/butler/assets/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5182,
    strictPort: true,
    open: false,
    allowedHosts: ["desktop-g62m1s8.taild55c40.ts.net"],
    proxy: {
      "/butler/assets/api": {
        target: "http://127.0.0.1:8765",
        rewrite: (path) => path.replace(/^\/butler\/assets/, "")
      },
      "/butler/assets/asset": {
        target: "http://127.0.0.1:8765",
        rewrite: (path) => path.replace(/^\/butler\/assets/, "")
      },
      "/api": "http://127.0.0.1:8765",
      "/asset": "http://127.0.0.1:8765"
    }
  },
  test: {
    environment: "jsdom",
    globals: true
  }
});
