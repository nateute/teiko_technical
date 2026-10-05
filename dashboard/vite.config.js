import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // needed so Codespaces can forward the port
    port: 5173,
    proxy: { "/api": "http://localhost:3001" },
  },
});
