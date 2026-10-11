import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The control plane serves the build same-origin at /admin; the output is gitignored.
export default defineConfig({
  base: "/admin/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../src/forge/web/admin",
    emptyOutDir: true,
    // CSP is `font-src 'self'; img-src 'self'`: no data: URIs, every asset is a real file.
    assetsInlineLimit: 0,
  },
  server: { host: "127.0.0.1", port: 3414, strictPort: true },
});
