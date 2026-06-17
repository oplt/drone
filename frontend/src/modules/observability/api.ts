import { httpRequest } from "../../shared/api/httpClient";
import type {
  ObservabilityContextOptions,
  ObservabilityLinks,
  ObservabilityStatus,
} from "./types";

export function fetchObservabilityLinks(signal?: AbortSignal) {
  return httpRequest<ObservabilityLinks>("/api/observability/links", { signal });
}

export function fetchObservabilityStatus(signal?: AbortSignal) {
  return httpRequest<ObservabilityStatus>("/api/observability/status", { signal });
}

export function fetchObservabilityContextOptions(signal?: AbortSignal) {
  return httpRequest<ObservabilityContextOptions>("/api/observability/context-options", {
    signal,
  });
}
