import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { AdminRuntimeLogFile } from "../api/adminApi";
import { downloadAdminDiagnosticsBundle, fetchAdminRuntimeLogs } from "../api/adminApi";
import { formatAdminBytes } from "../utils/adminFormat";

export function AdminDiagnosticsTab() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin-runtime-logs"],
    queryFn: () => fetchAdminRuntimeLogs(),
  });

  const downloadBundle = useMutation({
    mutationFn: () => downloadAdminDiagnosticsBundle(),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
        <Box>
          <Typography variant="subtitle2">Runtime Diagnostics</Typography>
          {data?.runtime_log_root && (
            <Typography variant="caption" color="text.secondary">
              {data.runtime_log_root}
            </Typography>
          )}
        </Box>
        <Stack direction="row" spacing={1}>
          <ActionIconButton variant="refresh" title="Refresh logs" onClick={() => refetch()} />
          <ActionIconButton
            variant="download"
            title="Download diagnostics bundle"
            loading={downloadBundle.isPending}
            onClick={() => downloadBundle.mutate()}
          />
        </Stack>
      </Stack>
      {isLoading && <CircularProgress />}
      {error && <Alert severity="error">Failed to load runtime logs</Alert>}
      {downloadBundle.error && (
        <Alert severity="error">Diagnostics bundle could not be downloaded</Alert>
      )}
      {data && data.logs.length === 0 && (
        <Alert severity="info">No runtime log files found yet</Alert>
      )}
      {data && data.logs.length > 0 && (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Source</TableCell>
              <TableCell>File</TableCell>
              <TableCell>Size</TableCell>
              <TableCell>Modified</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {data.logs.map((log: AdminRuntimeLogFile) => (
              <TableRow
                key={`${log.source}:${log.relative_path}:${log.modified_at}`}
                hover
              >
                <TableCell>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Chip label={log.source} size="small" variant="outlined" />
                    {log.legacy && <Chip label="legacy" size="small" color="warning" />}
                  </Stack>
                </TableCell>
                <TableCell sx={{ fontSize: 12 }}>{log.relative_path}</TableCell>
                <TableCell>{formatAdminBytes(log.size_bytes)}</TableCell>
                <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
                  {new Date(log.modified_at).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Stack>
  );
}
