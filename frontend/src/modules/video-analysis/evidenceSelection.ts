export function selectDetectionEvidence(evidenceId: string | null): void {
  const url = new URL(window.location.href);
  if (evidenceId) {
    url.searchParams.set("evidence", evidenceId);
    url.searchParams.set("type", "detection");
  } else {
    url.searchParams.delete("evidence");
    url.searchParams.delete("type");
  }
  window.history.replaceState(window.history.state, "", url);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function selectedDetectionEvidence(): string | null {
  const search = new URLSearchParams(window.location.search);
  return search.get("type") === "detection" ? search.get("evidence") : null;
}
