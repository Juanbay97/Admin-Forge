import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyBrandTheme, defaultTheme } from "./brand/theme";
import "./brand/tokens.css";

applyBrandTheme(defaultTheme);

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");
const react = createRoot(root);
const kit = new URLSearchParams(window.location.search).get("kit");

if (import.meta.env.VITE_KIT === "1" && kit) {
  // UI-test build only: the constant is replaced at compile time, so a production bundle contains no gallery.
  void import("./ui/gallery").then(({ Gallery }) =>
    react.render(
      <StrictMode>
        <Gallery name={kit} />
      </StrictMode>,
    ),
  );
} else {
  react.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
