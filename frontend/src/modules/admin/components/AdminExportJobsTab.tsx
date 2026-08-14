import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Chip,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from "@mui/material";

import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { fetchAdminExportJobs } from "../api/adminApi";
import type { AdminExportJobsResponse } from "../adminTypes";

export function AdminExportJobsTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-export-jobs"],
    queryFn: () => fetchAdminExportJobs<AdminExportJobsResponse>(),
  });

  if (isLoading) return <CircularProgress />;
  if (error) return <Alert severity="error">Failed to load export jobs</Alert>;

  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>ID</TableCell>
          <TableCell>Org</TableCell>
          <TableCell>Flight ID</TableCell>
          <TableCell>Status</TableCell>
          <TableCell>Created</TableCell>
          <TableCell>Download</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {(data?.jobs ?? []).map((job) => (
          <TableRow key={job.id} hover>
            <TableCell>{job.id}</TableCell>
            <TableCell>{job.org_id ?? "—"}</TableCell>
            <TableCell sx={{ fontSize: 11 }}>{job.flight_id}</TableCell>
            <TableCell>
              <Chip
                label={job.status}
                size="small"
                color={
                  job.status === "ready"
                    ? "success"
                    : job.status === "failed"
                      ? "error"
                      : "default"
                }
              />
            </TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {new Date(job.created_at).toLocaleDateString()}
            </TableCell>
            <TableCell>
              {job.download_url != null && (
                <ActionIconButton
                  variant="download"
                  title="Download"
                  onClick={() => window.open(job.download_url ?? undefined, "_blank")}
                />
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
