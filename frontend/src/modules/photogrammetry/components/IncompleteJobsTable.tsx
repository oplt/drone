import {
  Button,
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from "@mui/material";
import type { MappingJobRecord } from "../types";

type IncompleteJobsTableProps = {
  jobs: MappingJobRecord[];
  onDelete: (jobId: number) => void;
  onResume: (jobId: number) => void;
};

export function IncompleteJobsTable({ jobs, onDelete, onResume }: IncompleteJobsTableProps) {
  const incompleteJobs = jobs.filter(
    (job) => job.status !== "ready" && job.status !== "failed",
  );

  if (incompleteJobs.length === 0) {
    return null;
  }

  return (
    <TableContainer component={Paper} sx={{ mt: 2 }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Job ID</TableCell>
            <TableCell>Field ID</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Progress</TableCell>
            <TableCell>Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {incompleteJobs.map((job) => (
            <TableRow key={job.job_id}>
              <TableCell>{job.job_id}</TableCell>
              <TableCell>{job.field_id}</TableCell>
              <TableCell>{job.status}</TableCell>
              <TableCell>
                <LinearProgress variant="determinate" value={job.progress} />
              </TableCell>
              <TableCell>
                <Stack direction="row" spacing={1}>
                  <Button size="small" variant="outlined" onClick={() => onResume(job.job_id)}>
                    Resume
                  </Button>
                  <Button
                    size="small"
                    color="error"
                    variant="outlined"
                    onClick={() => onDelete(job.job_id)}
                  >
                    Delete
                  </Button>
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
