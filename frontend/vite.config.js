import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// En desarrollo, /api va al backend local (uvicorn en :8000).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
