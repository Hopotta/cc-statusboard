import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  root: ".",
  publicDir: "public", // explicitly enable: statusboard.json is copied here
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
    open: false,
    strictPort: true,
    fs: {
      allow: [".."],
    },
  },
  preview: {
    port: 5173,
    host: "127.0.0.1",
    fs: {
      allow: [".."],
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});