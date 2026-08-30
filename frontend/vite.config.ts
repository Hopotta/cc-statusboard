import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";

// Single data source: the root statusboard.json, the same file the Python
// server serves in production.
function freshStatusboard(): Plugin {
  return {
    name: "fresh-statusboard",
    configureServer(server) {
      server.middlewares.use("/statusboard.json", (_req, res) => {
        const file = path.resolve(__dirname, "../statusboard.json");
        if (!fs.existsSync(file)) {
          res.statusCode = 404;
          res.end("statusboard.json not found - run `python collector/generate_statusboard.py --once`");
          return;
        }
        res.setHeader("Content-Type", "application/json");
        res.setHeader("Cache-Control", "no-store");
        fs.createReadStream(file).pipe(res);
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), freshStatusboard()],
  root: ".",
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