import { Suspense, lazy, type ReactNode } from "react";
import { PageLoader } from "../../shared/ui";

const STALE_CHUNK_RELOAD_KEY = "drone-app:stale-chunk-reload";

function isStaleChunkError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  return /Failed to fetch dynamically imported module|Importing a module script failed|Loading chunk .* failed|error loading dynamically imported module/i.test(
    message,
  );
}

export function lazyWithStaleChunkReload<P extends object>(
  importer: () => Promise<{ default: React.ComponentType<P> }>,
) {
  return lazy(() =>
    importer().catch((error) => {
      if (isStaleChunkError(error) && sessionStorage.getItem(STALE_CHUNK_RELOAD_KEY) !== "1") {
        sessionStorage.setItem(STALE_CHUNK_RELOAD_KEY, "1");
        window.location.reload();
        return new Promise<{ default: React.ComponentType<P> }>(() => {});
      }
      throw error;
    }),
  );
}

if (typeof window !== "undefined") {
  window.addEventListener("load", () => {
    sessionStorage.removeItem(STALE_CHUNK_RELOAD_KEY);
  });
}

export function renderLazyRoute(node: ReactNode, fullScreen = false) {
  return (
    <Suspense fallback={<PageLoader fullScreen={fullScreen} />}>
      {node}
    </Suspense>
  );
}
