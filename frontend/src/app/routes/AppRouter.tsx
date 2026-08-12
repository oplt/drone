import { lazy, Suspense } from "react";
import type { ReactElement } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import type { HomeProps } from "../../modules/session/views/LandingPage";
import { GuestRoute } from "./GuestRoute";
import { ProtectedRoute } from "./ProtectedRoute";
import { lazyWithStaleChunkReload, renderLazyRoute } from "./routeLoaders";

const LandingPage = lazyWithStaleChunkReload<HomeProps>(
  () => import("../../modules/session/views/LandingPage"),
);
const DashboardShell = lazyWithStaleChunkReload(
  () => import("../../modules/dashboard/views/DashboardShell"),
);
const DashboardHome = lazyWithStaleChunkReload(
  () => import("../../modules/dashboard/views/DashboardHomePage"),
);
const AdminSettingsPage = lazyWithStaleChunkReload(
  () => import("../../modules/settings/views/AdminSettingsPage"),
);
const AccountPage = lazyWithStaleChunkReload(
  () => import("../../modules/dashboard/views/AccountPage"),
);
const InsightsPage = lazyWithStaleChunkReload(
  () => import("../../modules/dashboard/views/InsightsPage"),
);
const FleetPage = lazyWithStaleChunkReload(() => import("../../modules/fleet"));
const ControlledFlightPage = lazyWithStaleChunkReload(
  () => import("../../modules/controlled-flight"),
);
const PhotoGrammetryPage = lazyWithStaleChunkReload(
  () => import("../../modules/photogrammetry"),
);
const FieldPage = lazyWithStaleChunkReload(
  () => import("../../modules/field-survey"),
);
const AgricultureFieldListPage = lazyWithStaleChunkReload(
  () => import("../../modules/agriculture/views/AgricultureFieldListPage"),
);
const AgricultureFieldDetailPage = lazyWithStaleChunkReload(
  () => import("../../modules/agriculture/views/AgricultureFieldDetailPage"),
);
const AgricultureFlightPage = lazyWithStaleChunkReload(
  () => import("../../modules/agriculture/views/AgricultureFlightPage"),
);
const AgricultureAnalysisPage = lazyWithStaleChunkReload(
  () => import("../../modules/agriculture/views/AgricultureAnalysisPage"),
);
const AgricultureVisionModelsPage = lazyWithStaleChunkReload(
  () => import("../../modules/agriculture/views/AgricultureVisionModelsPage"),
);
const AgricultureLabelingWorkspace = lazyWithStaleChunkReload(
  () => import("../../modules/agriculture/views/LabelingWorkspace"),
);
const WarehousePage = lazyWithStaleChunkReload(
  () => import("../../modules/warehouse"),
);
const AnimalFarmPage = lazyWithStaleChunkReload(
  () => import("../../modules/animal-farm"),
);
const PrivatePatrolPage = lazyWithStaleChunkReload(
  () => import("../../modules/private-patrol"),
);
const PropertyPatrolPage = lazyWithStaleChunkReload(
  () => import("../../modules/property-patrol"),
);
const MissionTimeline = lazyWithStaleChunkReload(
  () => import("../../modules/mission-history"),
);
const AdminPage = lazyWithStaleChunkReload(() => import("../../modules/admin"));
const TemplatesPage = lazyWithStaleChunkReload(
  () => import("../../modules/templates"),
);
const VideoAnalysisPage = lazyWithStaleChunkReload(
  () => import("../../modules/video-analysis"),
);
const ObservabilityPage = lazyWithStaleChunkReload(
  () => import("../../modules/observability"),
);
const MapProviders = lazy(() => import("../providers/MapProviders"));

function renderMapRoute(element: ReactElement) {
  return (
    <Suspense
      fallback={
        <div role="status" aria-live="polite" aria-busy="true">
          Loading map services…
        </div>
      }
    >
      <MapProviders>{renderLazyRoute(element)}</MapProviders>
    </Suspense>
  );
}

export function AppRouter() {
  return (
    <BrowserRouter
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <Routes>
        <Route
          path="/"
          element={
            <GuestRoute>{renderLazyRoute(<LandingPage />, true)}</GuestRoute>
          }
        />
        <Route
          path="/signin"
          element={
            <GuestRoute>
              {renderLazyRoute(<LandingPage initialAuthMode="signIn" />, true)}
            </GuestRoute>
          }
        />
        <Route
          path="/signup"
          element={
            <GuestRoute>
              {renderLazyRoute(<LandingPage initialAuthMode="signUp" />, true)}
            </GuestRoute>
          }
        />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              {renderLazyRoute(<DashboardShell />, true)}
            </ProtectedRoute>
          }
        >
          <Route index element={renderLazyRoute(<DashboardHome />)} />
          <Route path="insights" element={renderLazyRoute(<InsightsPage />)} />
          <Route path="fleet" element={renderLazyRoute(<FleetPage />)} />
          <Route
            path="settings"
            element={renderLazyRoute(<AdminSettingsPage />)}
          />
          <Route
            path="controlled"
            element={renderMapRoute(<ControlledFlightPage />)}
          />
          <Route path="account" element={renderLazyRoute(<AccountPage />)} />
          <Route
            path="photogrammetry"
            element={renderMapRoute(<PhotoGrammetryPage />)}
          />
          <Route
            path="animalfarm"
            element={renderMapRoute(<AnimalFarmPage />)}
          />
          <Route
            path="privatepatrol"
            element={renderMapRoute(<PrivatePatrolPage />)}
          />
          <Route
            path="property-patrol"
            element={renderMapRoute(<PropertyPatrolPage />)}
          />
          <Route path="field" element={renderMapRoute(<FieldPage />)} />
          <Route
            path="agriculture/fields"
            element={renderMapRoute(<AgricultureFieldListPage />)}
          />
          <Route
            path="agriculture/fields/:fieldId"
            element={renderMapRoute(<AgricultureFieldDetailPage />)}
          />
          <Route
            path="agriculture/flights/:flightId"
            element={renderMapRoute(<AgricultureFlightPage />)}
          />
          <Route
            path="agriculture/analysis/:runId"
            element={renderMapRoute(<AgricultureAnalysisPage />)}
          />
          <Route
            path="agriculture/vision-models"
            element={renderLazyRoute(<AgricultureVisionModelsPage />)}
          />
          <Route
            path="agriculture/vision-models/datasets/:datasetId/label"
            element={renderLazyRoute(<AgricultureLabelingWorkspace />)}
          />
          <Route
            path="warehouse"
            element={renderMapRoute(<WarehousePage />)}
          />
          <Route path="admin" element={renderLazyRoute(<AdminPage />)} />
          <Route
            path="templates"
            element={renderLazyRoute(<TemplatesPage />)}
          />
          <Route
            path="video-analysis"
            element={renderLazyRoute(<VideoAnalysisPage />)}
          />
          <Route
            path="observability"
            element={renderLazyRoute(<ObservabilityPage />)}
          />
        </Route>
        <Route
          path="/observability"
          element={
            <ProtectedRoute>
              {renderLazyRoute(<DashboardShell />, true)}
            </ProtectedRoute>
          }
        >
          <Route index element={renderLazyRoute(<ObservabilityPage />)} />
        </Route>
        <Route
          path="/admin/settings"
          element={
            <ProtectedRoute>
              {renderLazyRoute(<DashboardShell />, true)}
            </ProtectedRoute>
          }
        >
          <Route
            index
            element={renderLazyRoute(
              <AdminSettingsPage initialTab="profile" />,
            )}
          />
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
