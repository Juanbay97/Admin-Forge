import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// The control plane serves the build same-origin at /admin; the output is gitignored. `landing.html` is a second entry of the same
// bundle (same assets, same strict CSP): the control plane serves it at the domain root `/`.
export default defineConfig({
  base: "/admin/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../src/forge/web/admin",
    emptyOutDir: true,
    rollupOptions: { input: { main: fileURLToPath(new URL("index.html", import.meta.url)), landing: fileURLToPath(new URL("landing.html", import.meta.url)) } },
    // CSP is `font-src 'self'; img-src 'self'`: no data: URIs, every asset is a real file.
    assetsInlineLimit: 0,
  },
  server: { host: "127.0.0.1", port: 3414, strictPort: true },
});
