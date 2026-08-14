import { Component, type ErrorInfo, type ReactNode } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import { Link as RouterLink } from "react-router-dom";
import ErrorState from "./ErrorState";

type RouteErrorBoundaryProps = {
  children: ReactNode;
  /** Optional home path for recover CTA. */
  homeTo?: string;
};

type RouteErrorBoundaryState = {
  error: Error | null;
};

/**
 * Catches render/lazy-load failures so routes fail visibly
 * instead of white-screening (BrowserRouter has no errorElement).
 */
export class RouteErrorBoundary extends Component<
  RouteErrorBoundaryProps,
  RouteErrorBoundaryState
> {
  state: RouteErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): RouteErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.error("RouteErrorBoundary caught", error, info.componentStack);
    }
  }

  private handleRetry = () => {
    this.setState({ error: null });
  };

  private handleReload = () => {
    window.location.reload();
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const homeTo = this.props.homeTo ?? "/dashboard";
    const message =
      error.message?.trim() ||
      "This view failed to load. Retry, or return to Operations.";

    return (
      <ErrorState
        title="View failed to load"
        message={message}
        onRetry={this.handleRetry}
        retryLabel="Retry"
        action={
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" size="small" onClick={this.handleReload}>
              Reload page
            </Button>
            <Button
              component={RouterLink}
              to={homeTo}
              variant="contained"
              size="small"
              onClick={this.handleRetry}
            >
              Operations
            </Button>
          </Stack>
        }
      />
    );
  }
}

export default RouteErrorBoundary;
