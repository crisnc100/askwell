import { defineConfig } from "vite";
import { resolve } from "node:path";

// `npm run dev` serves the page on its own port and sends API calls to a local
// `uvicorn askwell.api:create_app --factory` on port 8000.
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        results: resolve(__dirname, "results/index.html"),
        value: resolve(__dirname, "value/index.html"),
      },
    },
  },
});
