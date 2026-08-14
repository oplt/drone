import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { fetchAdminMappingJobs, requeueMappingJob } from "../api/adminApi";
import type { AdminMappingJobsResponse } from "../adminTypes";

export function AdminMappingJobsTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-mapping-jobs"],
    queryFn: () => fetchAdminMappingJobs<AdminMappingJobsResponse>(),
  });

  const requeue = useMutation({
    mutationFn: (jobId: number) => requeueMappingJob(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-mapping-jobs"] }),
  });

  if (isLoading) return <CircularProgress />;
  if (error) return <Alert severity="error">Failed to load mapping jobs</Alert>;

  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>ID</TableCell>
          <TableCell>Field</TableCell>
          <TableCell>Status</TableCell>
          <TableCell>Progress</TableCell>
          <TableCell>Created</TableCell>
          <TableCell>Finished</TableCell>
          <TableCell></TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {(data?.jobs ?? []).map((job) => (
          <TableRow key={job.id} hover>
            <TableCell>{job.id}</TableCell>
            <TableCell>{job.field_id}</TableCell>
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
            <TableCell>{job.progress}%</TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {new Date(job.created_at).toLocaleDateString()}
            </TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {job.finished_at ? new Date(job.finished_at).toLocaleDateString() : "—"}
            </TableCell>
            <TableCell>
              {(job.status === "failed" || job.status === "pending") && (
                <ActionIconButton
                  variant="retry"
                  title="Requeue"
                  loading={requeue.isPending}
                  onClick={() => requeue.mutate(job.id)}
                />
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
