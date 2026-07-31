import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(() => {
  const workbenchTarget = `http://127.0.0.1:${process.env.ASSET_REVIEW_PORT || "8765"}`;
  return {
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
          target: workbenchTarget,
          rewrite: (path) => path.replace(/^\/butler\/assets/, "")
        },
        "/butler/assets/asset": {
          target: workbenchTarget,
          rewrite: (path) => path.replace(/^\/butler\/assets/, "")
        },
        "/api": workbenchTarget,
        "/asset": workbenchTarget
      }
    },
    test: {
      environment: "jsdom",
      globals: true
    }
  };
});
