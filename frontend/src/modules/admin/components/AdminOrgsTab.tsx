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

import { fetchAdminOrganizations } from "../api/adminApi";
import type { AdminOrganizationsResponse } from "../adminTypes";

export function AdminOrgsTab() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-orgs"],
    queryFn: () => fetchAdminOrganizations<AdminOrganizationsResponse>(),
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
        {(data?.organizations ?? []).map((org) => (
          <TableRow key={org.id} hover>
            <TableCell>{org.id}</TableCell>
            <TableCell>{org.name}</TableCell>
            <TableCell>
              <Chip label={org.slug} size="small" variant="outlined" />
            </TableCell>
            <TableCell>{org.user_count}</TableCell>
            <TableCell sx={{ fontSize: 11, color: "text.secondary" }}>
              {new Date(org.created_at).toLocaleDateString()}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
