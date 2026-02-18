import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./output.css";
import "cesium/Build/Cesium/Widgets/widgets.css";


const container = document.getElementById("root");
if (!container) throw new Error('Root element "#root" not found');

const root = createRoot(container);

root.render(
  <StrictMode>
    <App />
  </StrictMode>
);
