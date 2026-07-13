import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import RefreshRoundedIcon from "@mui/icons-material/RefreshRounded";
import {
  fetchWarehouseCoordinateDiagnostics,
  syncWarehouseCoordinateFrameToRos,
  type WarehouseCoordinateDiagnostics,
} from "../api/warehouseInspectionApi";

export function WarehouseCoordinateDiagnosticsPanel({
  warehouseMapId,
  token,
}: {
  warehouseMapId: number;
  token?: string | null;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState<WarehouseCoordinateDiagnostics | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      setDiagnostics(await fetchWarehouseCoordinateDiagnostics(warehouseMapId, token, controller.signal));
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      setDiagnostics(null);
      setError(err instanceof Error ? err.message : "Failed to load coordinate diagnostics");
    } finally {
      setLoading(false);
    }
  }, [token, warehouseMapId]);

  const syncRos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await syncWarehouseCoordinateFrameToRos(warehouseMapId, token);
      await refresh();
      if (!result.synced) {
        setError(result.detail);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to sync localization to ROS");
    } finally {
      setLoading(false);
    }
  }, [refresh, token, warehouseMapId]);

  useEffect(() => {
    void refresh();
    return () => requestRef.current?.abort();
  }, [refresh]);

  const frame = diagnostics?.coordinate_frame;
  const layout = diagnostics?.layout_version;

  return (
    <Box sx={{ p: 1.25, border: "1px solid", borderColor: "divider", borderRadius: 1 }}>
      <Stack spacing={1}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="subtitle2">Coordinate diagnostics</Typography>
          {diagnostics ? (
            <Chip
              size="small"
              label={diagnostics.mission_ready ? "Mission ready" : "Blocked"}
              color={diagnostics.mission_ready ? "success" : "warning"}
            />
          ) : null}
          <Button
            size="small"
            startIcon={loading ? <CircularProgress size={14} /> : <RefreshRoundedIcon />}
            onClick={() => void refresh()}
            disabled={loading}
          >
            Refresh
          </Button>
          <Button size="small" variant="outlined" onClick={() => void syncRos()} disabled={loading}>
            Sync ROS TF
          </Button>
        </Stack>

        {error ? <Alert severity="error">{error}</Alert> : null}

        {diagnostics ? (
          <>
            <Typography variant="caption" color="text.secondary" component="div">
              Frame{" "}
              {frame
                ? `warehouse_map v${frame.version} (${frame.child_frame_id})`
                : "not locked"}
              {" · "}
              Layout {layout ? `v${layout.version} rev ${layout.revision}` : "not locked"}
              {typeof frame?.transform_age_ms === "number"
                ? ` · transform age ${(frame.transform_age_ms / 1000).toFixed(0)}s`
                : ""}
            </Typography>

            {diagnostics.ros_map_odom_tf ? (
              <Typography variant="caption" color="text.secondary">
                ROS TF warehouse_map→odom:{" "}
                {diagnostics.ros_map_odom_tf.tf_ok ? "connected" : "missing"}
              </Typography>
            ) : null}

            {diagnostics.ros_tf_tree ? (
              <Box>
                <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 0.5 }}>
                  ROS TF tree:{" "}
                  {diagnostics.ros_tf_tree.tf_ok
                    ? `all ${diagnostics.ros_tf_tree.edge_count ?? 0} edges connected`
                    : `${diagnostics.ros_tf_tree.ok_count ?? 0}/${diagnostics.ros_tf_tree.edge_count ?? 0} edges connected`}
                </Typography>
                <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
                  {(diagnostics.ros_tf_tree.edges ?? []).map((edge) => (
                    <Chip
                      key={`${edge.parent_frame}->${edge.child_frame}`}
                      size="small"
                      variant="outlined"
                      color={edge.tf_ok ? "success" : "warning"}
                      label={`${edge.parent_frame}→${edge.child_frame}`}
                      title={edge.detail ?? undefined}
                    />
                  ))}
                </Stack>
              </Box>
            ) : null}

            {diagnostics.slam_localization ? (
              <Typography variant="caption" color="text.secondary">
                SLAM localization:{" "}
                {diagnostics.slam_localization.healthy ? "healthy" : "stale/low confidence"}
                {typeof diagnostics.slam_localization.confidence === "number"
                  ? ` · confidence ${diagnostics.slam_localization.confidence.toFixed(2)}`
                  : ""}
              </Typography>
            ) : null}

            {Object.keys(diagnostics.entity_counts).length > 0 ? (
              <Typography variant="caption" color="text.secondary">
                Entities:{" "}
                {Object.entries(diagnostics.entity_counts)
                  .map(([kind, count]) => `${kind} ${count}`)
                  .join(" · ")}
              </Typography>
            ) : null}

            {diagnostics.blocking_issues.map((issue) => (
              <Alert key={issue.code} severity="error">
                {issue.message}
              </Alert>
            ))}
            {diagnostics.warnings.map((issue) => (
              <Alert key={issue.code} severity="warning">
                {issue.message}
              </Alert>
            ))}
          </>
        ) : null}
      </Stack>
    </Box>
  );
}
