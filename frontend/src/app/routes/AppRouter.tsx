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
const FieldPage = lazyWithStaleChunkReload(() => import("../../modules/field-survey"));
const WarehousePage = lazyWithStaleChunkReload(() => import("../../modules/warehouse"));
const AnimalFarmPage = lazyWithStaleChunkReload(() => import("../../modules/animal-farm"));
const PrivatePatrolPage = lazyWithStaleChunkReload(
  () => import("../../modules/private-patrol"),
);
const PropertyPatrolPage = lazyWithStaleChunkReload(
  () => import("../../modules/property-patrol"),
);
const MissionTimeline = lazyWithStaleChunkReload(() => import("../../modules/mission-history"));
const AdminPage = lazyWithStaleChunkReload(() => import("../../modules/admin"));
const TemplatesPage = lazyWithStaleChunkReload(() => import("../../modules/templates"));
const VideoAnalysisPage = lazyWithStaleChunkReload(() => import("../../modules/video-analysis"));

export function AppRouter() {
  return (
    <BrowserRouter
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
    >
      <Routes>
        <Route
          path="/"
          element={
            <GuestRoute>
              {renderLazyRoute(<LandingPage />, true)}
            </GuestRoute>
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
          <Route path="settings" element={renderLazyRoute(<AdminSettingsPage />)} />
          <Route path="controlled" element={renderLazyRoute(<ControlledFlightPage />)} />
          <Route path="account" element={renderLazyRoute(<AccountPage />)} />
          <Route path="photogrammetry" element={renderLazyRoute(<PhotoGrammetryPage />)} />
          <Route path="animalfarm" element={renderLazyRoute(<AnimalFarmPage />)} />
          <Route path="privatepatrol" element={renderLazyRoute(<PrivatePatrolPage />)} />
          <Route path="property-patrol" element={renderLazyRoute(<PropertyPatrolPage />)} />
          <Route path="field" element={renderLazyRoute(<FieldPage />)} />
          <Route path="warehouse" element={renderLazyRoute(<WarehousePage />)} />
          <Route path="admin" element={renderLazyRoute(<AdminPage />)} />
          <Route path="templates" element={renderLazyRoute(<TemplatesPage />)} />
          <Route path="video-analysis" element={renderLazyRoute(<VideoAnalysisPage />)} />
        </Route>
        <Route
          path="/admin/settings"
          element={
            <ProtectedRoute>
              {renderLazyRoute(<DashboardShell />, true)}
            </ProtectedRoute>
          }
        >
          <Route index element={renderLazyRoute(<AdminSettingsPage initialTab="profile" />)} />
        </Route>
        <Route path="/profile" element={<Navigate to="/admin/settings" replace />} />
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
