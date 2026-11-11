import { defineConfig } from "vite";

// `npm run dev` serves the page on its own port and sends API calls to a local
// `uvicorn ledgerline.api:create_app --factory` on port 8000.
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
