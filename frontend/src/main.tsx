import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import InitColorSchemeScript from "@mui/material/InitColorSchemeScript";
import App from "./app/App.tsx";
import { AppProviders } from "./app/providers/AppProviders.tsx";
import "./output.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error('Root element "#root" not found');
}

createRoot(container).render(
  <StrictMode>
    <InitColorSchemeScript attribute="data-mui-color-scheme" defaultMode="system" />
    <AppProviders>
      <App />
    </AppProviders>
  </StrictMode>,
);
