import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createDownloadsApi } from "../api/downloads";
import { applyBrandTheme, defaultTheme } from "../brand/theme";
import "../brand/tokens.css";
import { Landing } from "./Landing";

// The public landing is a static page of the admin bundle: no session, no authenticated call, only the public installer manifest.
applyBrandTheme(defaultTheme);

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");
createRoot(root).render(
  <StrictMode>
    <Landing downloads={createDownloadsApi()} />
  </StrictMode>,
);
