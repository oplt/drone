import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box,
  Chip,
  CircularProgress,
  FormControl,
  MenuItem,
  Paper,
  Select,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tabs,
  Typography,
  Stack,
  Alert,
} from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { AdminRuntimeLogFile } from "../api/adminApi";
import {
  downloadAdminDiagnosticsBundle,
  fetchAdminExportJobs,
  fetchAdminMappingJobs,
  fetchAdminOrganizations,
  fetchAdminRuntimeLogs,
  fetchAdminUsers,
  fetchAdminWorkerHealth,
  requeueMappingJob,
  updateUserRole,
} from "../api/adminApi";

const ROLES = [
  "admin",
  "org_admin",
  "ops_manager",
  "pilot",
  "viewer",
  "operator",
];

type AdminUser = {
  id: number;
  email: string;
  role: string;
  org_id: number | null;
  full_name: string | null;
  created_at: string;
};

type AdminUsersResponse = {
  users: AdminUser[];
};

type AdminOrganization = {
  id: number;
  name: string;
  slug: string;
  user_count: number;
  created_at: string;
};

type AdminOrganizationsResponse = {
  organizations: AdminOrganization[];
};

type AdminMappingJob = {
  id: number;
  field_id: number;
  status: string;
  progress: number;
  created_at: string;
  finished_at: string | null;
};

type AdminMappingJobsResponse = {
  jobs: AdminMappingJob[];
};

type AdminExportJob = {
  id: number;
  org_id: number | null;
  flight_id: string;
  status: string;
  download_url: string | null;
  created_at: string;
};

type AdminExportJobsResponse = {
  jobs: AdminExportJob[];
};

type AdminWorkerHealthResponse = {
  error?: string;
  workers?: string[];
  active_tasks?: Record<string, number>;
  reserved_tasks?: Record<string, number>;
  total_active?: number;
};

function UsersTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => fetchAdminUsers<AdminUsersResponse>(),
  });

  const updateRole = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string }) =>
      updateUserRole(userId, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  if (isLoading) return <CircularProgress />;
  if (error) return <Alert severity="error">Failed to load users</Alert>;

  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>ID</TableCell>
          <TableCell>Email</TableCell>
          <TableCell>Full Name</TableCell>
          <TableCell>Org ID</TableCell>
          <TableCell>Role</TableCell>
          <TableCell>Created</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {(data?.users ?? []).map((u) => (
          <TableRow key={u.id} hover>
            <TableCell>{u.id}</TableCell>
            <TableCell>{u.email}</TableCell>
            <TableCell>{u.full_name ?? "—"}</TableCell>
            <TableCell>{u.org_id ?? "—"}</TableCell>
            <TableCell>
              <FormControl size="small" variant="standard">
                <Select
                  value={u.role}
                  onChange={(e) =>
                    updateRole.mutate({ userId: u.id, role: e.target.value })
                  }
                  disabled={updateRole.isPending}
                  disableUnderline
                >
                  {ROLES.map((r) => (
                    <MenuItem key={r} value={r}>
                      {r}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {new Date(u.created_at).toLocaleDateString()}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function OrgsTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-orgs"],
    queryFn: () => fetchAdminOrganizations<AdminOrganizationsResponse>(),
  });

  if (isLoading) return <CircularProgress />;
  if (error)
    return <Alert severity="error">Failed to load organizations</Alert>;

  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>ID</TableCell>
          <TableCell>Name</TableCell>
          <TableCell>Slug</TableCell>
          <TableCell>Users</TableCell>
          <TableCell>Created</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {(data?.organizations ?? []).map((o) => (
          <TableRow key={o.id} hover>
            <TableCell>{o.id}</TableCell>
            <TableCell>{o.name}</TableCell>
            <TableCell>
              <Chip label={o.slug} size="small" variant="outlined" />
            </TableCell>
            <TableCell>{o.user_count}</TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {new Date(o.created_at).toLocaleDateString()}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function MappingJobsTab() {
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
        {(data?.jobs ?? []).map((j) => (
          <TableRow key={j.id} hover>
            <TableCell>{j.id}</TableCell>
            <TableCell>{j.field_id}</TableCell>
            <TableCell>
              <Chip
                label={j.status}
                size="small"
                color={
                  j.status === "ready"
                    ? "success"
                    : j.status === "failed"
                      ? "error"
                      : "default"
                }
              />
            </TableCell>
            <TableCell>{j.progress}%</TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {new Date(j.created_at).toLocaleDateString()}
            </TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {j.finished_at
                ? new Date(j.finished_at).toLocaleDateString()
                : "—"}
            </TableCell>
            <TableCell>
              {(j.status === "failed" || j.status === "pending") && (
                <ActionIconButton
                  variant="retry"
                  title="Requeue"
                  loading={requeue.isPending}
                  onClick={() => requeue.mutate(j.id)}
                />
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function ExportJobsTab() {
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
        {(data?.jobs ?? []).map((j) => (
          <TableRow key={j.id} hover>
            <TableCell>{j.id}</TableCell>
            <TableCell>{j.org_id ?? "—"}</TableCell>
            <TableCell sx={{ fontSize: 11 }}>{j.flight_id}</TableCell>
            <TableCell>
              <Chip
                label={j.status}
                size="small"
                color={
                  j.status === "ready"
                    ? "success"
                    : j.status === "failed"
                      ? "error"
                      : "default"
                }
              />
            </TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {new Date(j.created_at).toLocaleDateString()}
            </TableCell>
            <TableCell>
              {j.download_url != null && (
                <ActionIconButton
                  variant="download"
                  title="Download"
                  onClick={() =>
                    window.open(j.download_url ?? undefined, "_blank")
                  }
                />
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function WorkerHealthTab() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin-worker-health"],
    queryFn: () => fetchAdminWorkerHealth<AdminWorkerHealthResponse>(),
    refetchInterval: 10000,
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Typography variant="subtitle2">Worker Health</Typography>
        <ActionIconButton
          variant="refresh"
          title="Refresh"
          onClick={() => refetch()}
        />
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
            <Typography fontWeight={600}>
              {data.workers?.length ?? 0}
            </Typography>
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
                {(data.workers ?? []).map((w: string) => (
                  <TableRow key={w}>
                    <TableCell sx={{ fontSize: 11 }}>{w}</TableCell>
                    <TableCell>{data.active_tasks?.[w] ?? 0}</TableCell>
                    <TableCell>{data.reserved_tasks?.[w] ?? 0}</TableCell>
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

function formatBytes(sizeBytes: number): string {
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function DiagnosticsTab() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin-runtime-logs"],
    queryFn: () => fetchAdminRuntimeLogs(),
  });

  const downloadBundle = useMutation({
    mutationFn: () => downloadAdminDiagnosticsBundle(),
  });

  return (
    <Stack spacing={2}>
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        spacing={1}
      >
        <Box>
          <Typography variant="subtitle2">Runtime Diagnostics</Typography>
          {data?.runtime_log_root && (
            <Typography variant="caption" color="text.secondary">
              {data.runtime_log_root}
            </Typography>
          )}
        </Box>
        <Stack direction="row" spacing={1}>
          <ActionIconButton
            variant="refresh"
            title="Refresh logs"
            onClick={() => refetch()}
          />
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
        <Alert severity="error">
          Diagnostics bundle could not be downloaded
        </Alert>
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
                    {log.legacy && (
                      <Chip label="legacy" size="small" color="warning" />
                    )}
                  </Stack>
                </TableCell>
                <TableCell sx={{ fontSize: 12 }}>{log.relative_path}</TableCell>
                <TableCell>{formatBytes(log.size_bytes)}</TableCell>
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

const TABS = [
  "Users",
  "Organizations",
  "Mapping Jobs",
  "Export Jobs",
  "Worker Health",
  "Diagnostics",
];

export default function AdminPage() {
  const [tab, setTab] = useState(0);

  return (
    <Box sx={{ p: { xs: 2, md: 3 } }}>
      <Typography variant="h5" fontWeight={700} sx={{ mb: 2 }}>
        Admin Console
      </Typography>
      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}
      >
        {TABS.map((t) => (
          <Tab key={t} label={t} />
        ))}
      </Tabs>

      <Paper variant="outlined" sx={{ p: 2, overflow: "auto" }}>
        {tab === 0 && <UsersTab />}
        {tab === 1 && <OrgsTab />}
        {tab === 2 && <MappingJobsTab />}
        {tab === 3 && <ExportJobsTab />}
        {tab === 4 && <WorkerHealthTab />}
        {tab === 5 && <DiagnosticsTab />}
      </Paper>
    </Box>
  );
}
