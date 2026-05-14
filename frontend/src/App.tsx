import { Suspense, lazy, useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ProtectedRoute } from "./ProtectedRoute";
import { verifySession } from "./auth";
import PageLoader from "./components/shared/PageLoader";
import type { HomeProps } from "./pages/Home";
import "cesium/Build/Cesium/Widgets/widgets.css";

const STALE_CHUNK_RELOAD_KEY = "drone-app:stale-chunk-reload";

function isStaleChunkError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  return /Failed to fetch dynamically imported module|Importing a module script failed|Loading chunk .* failed|error loading dynamically imported module/i.test(
    message,
  );
}

function lazyWithStaleChunkReload<P extends object>(
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

window.addEventListener("load", () => {
  sessionStorage.removeItem(STALE_CHUNK_RELOAD_KEY);
});

const Home = lazyWithStaleChunkReload<HomeProps>(() => import("./pages/Home"));
const Dashboard = lazyWithStaleChunkReload(() => import("./pages/dashboard/Dashboard"));
const DashboardHome = lazyWithStaleChunkReload(() => import("./pages/dashboard/tabs/HomePage"));
const TasksPage = lazyWithStaleChunkReload(() => import("./pages/dashboard/tabs/TasksPage"));
const AdminSettingsPage = lazyWithStaleChunkReload(() => import("./pages/AdminSettingsPage"));
const AccountPage = lazyWithStaleChunkReload(() => import("./pages/dashboard/tabs/AccountPage"));
const InsightsPage = lazyWithStaleChunkReload(() => import("./pages/dashboard/tabs/InsightsPage"));
const FleetPage = lazyWithStaleChunkReload(() => import("./pages/dashboard/tabs/FleetPage"));
const TerrainPage = lazyWithStaleChunkReload(() => import("./pages/dashboard/tabs/TerrainPage"));
const ControlledFlightPage = lazyWithStaleChunkReload(
  () => import("./pages/dashboard/tabs/ControlledFlightPage"),
);
const PhotoGrammetryPage = lazyWithStaleChunkReload(
  () => import("./pages/dashboard/tabs/PhotoGrammetry"),
);
const FieldPage = lazyWithStaleChunkReload(() => import("./pages/dashboard/tabs/FieldPage"));
const WarehousePage = lazyWithStaleChunkReload(() => import("./pages/dashboard/tabs/Warehouse"));
const AnimalFarmPage = lazyWithStaleChunkReload(
  () => import("./pages/dashboard/tabs/AnimalFarmPage"),
);
const PrivatePatrolPage = lazyWithStaleChunkReload(
  () => import("./pages/dashboard/tabs/PrivatePatrolPage"),
);
const MissionTimeline = lazyWithStaleChunkReload(() => import("./pages/dashboard/MissionTimeline"));
const AdminPage = lazyWithStaleChunkReload(() => import("./pages/dashboard/tabs/AdminPage"));
const TemplatesPage = lazyWithStaleChunkReload(() => import("./pages/dashboard/tabs/TemplatesPage"));

function RedirectIfAuthenticated({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<"checking" | "authed" | "guest">("checking");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ok = await verifySession();
      if (cancelled) return;
      setStatus(ok ? "authed" : "guest");
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "checking") {
    return <PageLoader fullScreen />;
  }

  if (status === "authed") {
    return <Navigate to="/dashboard" replace />;
  }
  return <>{children}</>;
}

function renderLazyRoute(node: React.ReactNode, fullScreen = false) {
  return (
    <Suspense fallback={<PageLoader fullScreen={fullScreen} />}>
      {node}
    </Suspense>
  );
}

export default function App() {
  return (
    <BrowserRouter
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <Routes>
        <Route
          path="/"
          element={
            <RedirectIfAuthenticated>
              {renderLazyRoute(<Home />, true)}
            </RedirectIfAuthenticated>
          }
        />
        <Route
          path="/signin"
          element={
            <RedirectIfAuthenticated>
              {renderLazyRoute(<Home initialAuthMode="signIn" />, true)}
            </RedirectIfAuthenticated>
          }
        />
        <Route
          path="/signup"
          element={
            <RedirectIfAuthenticated>
              {renderLazyRoute(<Home initialAuthMode="signUp" />, true)}
            </RedirectIfAuthenticated>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              {renderLazyRoute(<Dashboard />, true)}
            </ProtectedRoute>
          }
        >
          <Route index element={renderLazyRoute(<DashboardHome />)} />
          <Route path="tasks" element={renderLazyRoute(<TasksPage />)} />
          <Route path="insights" element={renderLazyRoute(<InsightsPage />)} />
          <Route path="fleet" element={renderLazyRoute(<FleetPage />)} />
          <Route path="settings" element={renderLazyRoute(<AdminSettingsPage />)} />
          <Route path="terrain" element={renderLazyRoute(<TerrainPage />)} />
          <Route path="controlled" element={renderLazyRoute(<ControlledFlightPage />)} />
          <Route path="account" element={renderLazyRoute(<AccountPage />)} />
          <Route
            path="photogrammetry"
            element={renderLazyRoute(<PhotoGrammetryPage />)}
          />
          <Route path="animalfarm" element={renderLazyRoute(<AnimalFarmPage />)} />
          <Route
            path="privatepatrol"
            element={renderLazyRoute(<PrivatePatrolPage />)}
          />
          <Route path="field" element={renderLazyRoute(<FieldPage />)} />
          <Route path="warehouse" element={renderLazyRoute(<WarehousePage />)} />
          <Route path="admin" element={renderLazyRoute(<AdminPage />)} />
          <Route path="templates" element={renderLazyRoute(<TemplatesPage />)} />
        </Route>
        <Route
          path="/admin/settings"
          element={
            <ProtectedRoute>
              {renderLazyRoute(<Dashboard />, true)}
            </ProtectedRoute>
          }
        >
          <Route index element={renderLazyRoute(<AdminSettingsPage initialTab="profile" />)} />
        </Route>
        <Route
          path="/profile"
          element={<Navigate to="/admin/settings" replace />}
        />
        <Route
          path="/missions/:flightId/timeline"
          element={
            <ProtectedRoute>
              {renderLazyRoute(<MissionTimeline />)}
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
