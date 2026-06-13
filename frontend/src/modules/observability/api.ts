import { httpRequest } from "../../shared/api/httpClient";
import type { ObservabilityLinks, ObservabilityStatus } from "./types";

export function fetchObservabilityLinks(signal?: AbortSignal) {
  return httpRequest<ObservabilityLinks>("/api/observability/links", { signal });
}

export function fetchObservabilityStatus(signal?: AbortSignal) {
  return httpRequest<ObservabilityStatus>("/api/observability/status", { signal });
}
