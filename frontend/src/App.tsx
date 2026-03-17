import { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ProtectedRoute } from "./ProtectedRoute";
import { getToken } from "./auth";
import PageLoader from "./components/shared/PageLoader";
import "cesium/Build/Cesium/Widgets/widgets.css";

const Home = lazy(() => import("./pages/Home"));
const SignIn = lazy(() => import("./pages/SignIn"));
const SignUp = lazy(() => import("./pages/SignUp"));
const Dashboard = lazy(() => import("./pages/dashboard/Dashboard"));
const DashboardHome = lazy(() => import("./pages/dashboard/tabs/HomePage"));
const TasksPage = lazy(() => import("./pages/dashboard/tabs/TasksPage"));
const SettingsPage = lazy(() => import("./pages/dashboard/tabs/SettingsPage"));
const AccountPage = lazy(() => import("./pages/dashboard/tabs/AccountPage"));
const ProfilePage = lazy(() => import("./pages/dashboard/tabs/ProfilePage"));
const InsightsPage = lazy(() => import("./pages/dashboard/tabs/InsightsPage"));
const FleetPage = lazy(() => import("./pages/dashboard/tabs/FleetPage"));
const TerrainPage = lazy(() => import("./pages/dashboard/tabs/TerrainPage"));
const PhotoGrammetryPage = lazy(() => import("./pages/dashboard/tabs/PhotoGrammetry"));
const FieldPage = lazy(() => import("./pages/dashboard/tabs/FieldPage"));
const WarehousePage = lazy(() => import("./pages/dashboard/tabs/Warehouse"));
const AnimalFarmPage = lazy(() => import("./pages/dashboard/tabs/AnimalFarmPage"));
const PrivatePatrolPage = lazy(() => import("./pages/dashboard/tabs/PrivatePatrolPage"));

function RedirectIfAuthenticated({ children }: { children: React.ReactNode }) {
  const token = getToken();
  if (token) {
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
              {renderLazyRoute(<SignIn />, true)}
            </RedirectIfAuthenticated>
          }
        />
        <Route
          path="/signup"
          element={
            <RedirectIfAuthenticated>
              {renderLazyRoute(<SignUp />, true)}
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
          <Route path="settings" element={renderLazyRoute(<SettingsPage />)} />
          <Route path="terrain" element={renderLazyRoute(<TerrainPage />)} />
          <Route path="profile" element={renderLazyRoute(<ProfilePage />)} />
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
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
