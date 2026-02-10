import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home/Home";
import SignIn from "./pages/SignIn/SignIn";
import SignUp from "./pages/SignUp/SignUp";
import Dashboard from "./pages/dashboard/Dashboard";
import { ProtectedRoute } from "./ProtectedRoute";

import DashboardHome from "./pages/dashboard/tabs/HomePage";
import TasksPage from "./pages/dashboard/tabs/TasksPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/signin" element={<SignIn />} />
        <Route path="/signup" element={<SignUp />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        >
          <Route index element={<DashboardHome />} />
          <Route path="tasks" element={<TasksPage />} />

        </Route>
      </Routes>
    </BrowserRouter>
  );
}
