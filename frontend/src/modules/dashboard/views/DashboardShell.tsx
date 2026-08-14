import { Outlet, useNavigate } from "react-router-dom";
import { AlertCenterProvider } from "../../../modules/alerts";
import { useCurrentUser, logout } from "../../session";
import {
  chartsCustomizations,
  dataGridCustomizations,
  datePickersCustomizations,
} from "../../../shared/theme/customizations";
import { OperationsShell, WorkflowHeader } from "../../../shared/layout";
import { SystemLogsProvider } from "../../../shared/layout/SystemLogsProvider";
import { PageLoader, RouteErrorBoundary } from "../../../shared/ui";

const dashboardThemeComponents = {
  ...chartsCustomizations,
  ...dataGridCustomizations,
  ...datePickersCustomizations,
  MuiTextField: {
    defaultProps: {
      variant: "filled" as const,
    },
  },
};

export default function Dashboard(props: { disableCustomTheme?: boolean }) {
  const navigate = useNavigate();
  const { user, isLoading, isReady } = useCurrentUser();

  const handleLogout = async () => {
    await logout();
    navigate("/signin", { replace: true });
  };

  if (!isReady || isLoading) {
    return (
      <PageLoader
        fullScreen
        title="Loading console"
        subtitle="Checking access and preparing your operations workspace."
      />
    );
  }

  return (
    <AlertCenterProvider>
      <SystemLogsProvider>
        <OperationsShell
          user={user}
          onLogout={handleLogout}
          disableCustomTheme={props.disableCustomTheme}
          themeComponents={dashboardThemeComponents}
        >
          {/* Shared ops chrome: breadcrumbs, alerts, logs, honest link status */}
          <WorkflowHeader />
          <RouteErrorBoundary>
            <Outlet />
          </RouteErrorBoundary>
        </OperationsShell>
      </SystemLogsProvider>
    </AlertCenterProvider>
  );
}
