import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import mdx from "@mdx-js/rollup";

export default defineConfig({
  plugins: [mdx(), react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:10300", changeOrigin: true },
      "/socket.io": { target: "http://localhost:10300", ws: true },
    },
  },
  build: {
    manifest: true,
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
});
