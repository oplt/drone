import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Box, FormControl, MenuItem, Select, Stack, TextField } from "@mui/material";
import { DataGrid, type GridColDef } from "@mui/x-data-grid";

import { FeatureState } from "../../../shared/ui/FeatureState";
import { fetchAdminUsers, updateUserRole } from "../api/adminApi";
import { ADMIN_ROLES, type AdminUser, type AdminUsersResponse } from "../adminTypes";

export function AdminUsersTab() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => fetchAdminUsers<AdminUsersResponse>(),
  });

  const updateRole = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: string }) =>
      updateUserRole(userId, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
  });

  const rows = useMemo(() => {
    const query = search.trim().toLowerCase();
    const users = data?.users ?? [];
    if (!query) return users;
    return users.filter((user) => {
      const hay = `${user.id} ${user.email} ${user.full_name ?? ""} ${user.role} ${user.org_id ?? ""}`.toLowerCase();
      return hay.includes(query);
    });
  }, [data?.users, search]);

  const columns: GridColDef<AdminUser>[] = [
    { field: "id", headerName: "ID", width: 80 },
    { field: "email", headerName: "Email", flex: 1, minWidth: 180 },
    {
      field: "full_name",
      headerName: "Full Name",
      flex: 1,
      minWidth: 140,
      valueGetter: (_value, row) => row.full_name ?? "—",
    },
    {
      field: "org_id",
      headerName: "Org ID",
      width: 100,
      valueGetter: (_value, row) => row.org_id ?? "—",
    },
    {
      field: "role",
      headerName: "Role",
      width: 160,
      sortable: false,
      renderCell: (params) => (
        <FormControl size="small" variant="standard" sx={{ minWidth: 130 }}>
          <Select
            value={params.row.role}
            onChange={(event) =>
              updateRole.mutate({ userId: params.row.id, role: event.target.value })
            }
            disabled={updateRole.isPending}
            disableUnderline
          >
            {ADMIN_ROLES.map((role) => (
              <MenuItem key={role} value={role}>
                {role}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      ),
    },
    {
      field: "created_at",
      headerName: "Created",
      width: 180,
      valueGetter: (_value, row) =>
        row.created_at ? new Date(row.created_at).toLocaleDateString() : "—",
    },
  ];

  return (
    <Stack spacing={1.5}>
      <TextField
        size="small"
        label="Search users"
        placeholder="Email, name, role, org…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        sx={{ maxWidth: 360 }}
        inputProps={{ "aria-label": "Search users" }}
      />
      <FeatureState
        loading={isLoading}
        error={error ? "Failed to load users" : null}
        onRetry={() => void refetch()}
        empty={
          !isLoading && rows.length === 0
            ? {
                title: search.trim() ? "No matching users" : "No users",
                description: search.trim()
                  ? "Try a different search term."
                  : "No users are registered yet.",
              }
            : undefined
        }
      >
        <Box sx={{ height: 420, width: "100%" }}>
          <DataGrid
            rows={rows}
            columns={columns}
            getRowId={(row) => row.id}
            disableRowSelectionOnClick
            pageSizeOptions={[10, 25, 50]}
            initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
            density="compact"
          />
        </Box>
      </FeatureState>
    </Stack>
  );
}
