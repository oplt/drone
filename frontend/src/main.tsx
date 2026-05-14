import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./output.css";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./queryClient";
import { GoogleMapsProvider } from "./utils/googleMaps";

const originalFetch = window.fetch.bind(window);
const getFetchUrl = (input: RequestInfo | URL) => {
  if (input instanceof Request) return input.url;
  if (input instanceof URL) return input.href;
  return String(input);
};
const isSameOriginFetch = (input: RequestInfo | URL) => {
  try {
    return new URL(getFetchUrl(input), window.location.href).origin === window.location.origin;
  } catch {
    return true;
  }
};

window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const isSameOrigin = isSameOriginFetch(input);
  const res = await originalFetch(input, {
    ...init,
    credentials: init?.credentials ?? (isSameOrigin ? "include" : "omit"),
  });
  if (isSameOrigin && res.status === 401 && !getFetchUrl(input).includes("/auth/")) {
    window.location.replace("/signin");
  }
  return res;
};

const container = document.getElementById("root");
if (!container) throw new Error('Root element "#root" not found');

const root = createRoot(container);

root.render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <GoogleMapsProvider>
        <App />
      </GoogleMapsProvider>
    </QueryClientProvider>
  </StrictMode>
);
