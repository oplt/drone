import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
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
import RefreshIcon from "@mui/icons-material/Refresh";

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

const ROLES = ["admin", "org_admin", "ops_manager", "pilot", "viewer", "operator"];

function UsersTab() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<any>("/admin/users?page_size=100"),
  });

  const updateRole = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string }) =>
      apiFetch(`/admin/users/${userId}/role`, {
        method: "PUT",
        body: JSON.stringify({ role }),
      }),
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
        {(data?.users ?? []).map((u: any) => (
          <TableRow key={u.id} hover>
            <TableCell>{u.id}</TableCell>
            <TableCell>{u.email}</TableCell>
            <TableCell>{u.full_name ?? "—"}</TableCell>
            <TableCell>{u.org_id ?? "—"}</TableCell>
            <TableCell>
              <FormControl size="small" variant="standard">
                <Select
                  value={u.role}
                  onChange={(e) => updateRole.mutate({ userId: u.id, role: e.target.value })}
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
    queryFn: () => apiFetch<any>("/admin/organizations"),
  });

  if (isLoading) return <CircularProgress />;
  if (error) return <Alert severity="error">Failed to load organizations</Alert>;

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
        {(data?.organizations ?? []).map((o: any) => (
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
    queryFn: () => apiFetch<any>("/admin/mapping-jobs?page_size=100"),
  });

  const requeue = useMutation({
    mutationFn: (jobId: number) =>
      apiFetch(`/admin/mapping-jobs/${jobId}/requeue`, { method: "POST" }),
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
        {(data?.jobs ?? []).map((j: any) => (
          <TableRow key={j.id} hover>
            <TableCell>{j.id}</TableCell>
            <TableCell>{j.field_id}</TableCell>
            <TableCell>
              <Chip
                label={j.status}
                size="small"
                color={j.status === "ready" ? "success" : j.status === "failed" ? "error" : "default"}
              />
            </TableCell>
            <TableCell>{j.progress}%</TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {new Date(j.created_at).toLocaleDateString()}
            </TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {j.finished_at ? new Date(j.finished_at).toLocaleDateString() : "—"}
            </TableCell>
            <TableCell>
              {(j.status === "failed" || j.status === "pending") && (
                <Button
                  size="small"
                  onClick={() => requeue.mutate(j.id)}
                  disabled={requeue.isPending}
                >
                  Requeue
                </Button>
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
    queryFn: () => apiFetch<any>("/admin/export-jobs?page_size=100"),
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
        {(data?.jobs ?? []).map((j: any) => (
          <TableRow key={j.id} hover>
            <TableCell>{j.id}</TableCell>
            <TableCell>{j.org_id ?? "—"}</TableCell>
            <TableCell sx={{ fontSize: 11 }}>{j.flight_id}</TableCell>
            <TableCell>
              <Chip
                label={j.status}
                size="small"
                color={j.status === "ready" ? "success" : j.status === "failed" ? "error" : "default"}
              />
            </TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {new Date(j.created_at).toLocaleDateString()}
            </TableCell>
            <TableCell>
              {j.download_url && (
                <Button size="small" onClick={() => window.open(j.download_url, "_blank")}>
                  Download
                </Button>
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
    queryFn: () => apiFetch<any>("/admin/worker-health"),
    refetchInterval: 10000,
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <Typography variant="subtitle2">Worker Health</Typography>
        <Button size="small" startIcon={<RefreshIcon />} onClick={() => refetch()}>
          Refresh
        </Button>
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

const TABS = ["Users", "Organizations", "Mapping Jobs", "Export Jobs", "Worker Health"];

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
      </Paper>
    </Box>
  );
}
