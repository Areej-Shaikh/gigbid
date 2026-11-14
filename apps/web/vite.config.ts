import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, /api is proxied to FastAPI so the browser sees one origin (same as production).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } } },
});
