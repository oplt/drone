import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";

import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { fetchAdminWorkerHealth } from "../api/adminApi";
import type { AdminWorkerHealthResponse } from "../adminTypes";

export function AdminWorkerHealthTab() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin-worker-health"],
    queryFn: () => fetchAdminWorkerHealth<AdminWorkerHealthResponse>(),
    refetchInterval: 10000,
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Typography variant="subtitle2">Worker Health</Typography>
        <ActionIconButton variant="refresh" title="Refresh" onClick={() => refetch()} />
      </Stack>
      {isLoading && <CircularProgress />}
      {error && <Alert severity="error">Failed to reach workers</Alert>}
      {data?.error && <Alert severity="warning">{data.error}</Alert>}
      {data && !data.error && (
        <>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="caption" color="text.secondary">
              Workers online
            </Typography>
            <Typography fontWeight={600}>{data.workers?.length ?? 0}</Typography>
          </Paper>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Typography variant="caption" color="text.secondary">
              Active tasks (total)
            </Typography>
            <Typography fontWeight={600}>{data.total_active ?? 0}</Typography>
          </Paper>
          {(data.workers ?? []).length > 0 && (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Worker</TableCell>
                  <TableCell>Active</TableCell>
                  <TableCell>Reserved</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(data.workers ?? []).map((worker) => (
                  <TableRow key={worker}>
                    <TableCell sx={{ fontSize: 11 }}>{worker}</TableCell>
                    <TableCell>{data.active_tasks?.[worker] ?? 0}</TableCell>
                    <TableCell>{data.reserved_tasks?.[worker] ?? 0}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </>
      )}
    </Stack>
  );
}
