import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyBrandTheme, defaultTheme } from "./brand/theme";
import "./brand/tokens.css";

applyBrandTheme(defaultTheme);

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);