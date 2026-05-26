import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from "@mui/material";
import type { MissionCommandAuditResponse } from "../../types";
import { formatTs } from "./formatters";

export function CommandAuditSection({
  recentAudit,
  auditLoading,
  auditError,
}: {
  recentAudit: MissionCommandAuditResponse[];
  auditLoading: boolean;
  auditError: string | null;
}) {
  return (
    <Box sx={{ pt: 0.1 }}>
      <Typography
        variant="caption"
        sx={{ display: "block", mb: 0.6, letterSpacing: 0.6, fontWeight: 700 }}
      >
        COMMAND AUDIT
      </Typography>
      {auditError && <Alert severity="warning">{auditError}</Alert>}
      {auditLoading && recentAudit.length === 0 ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 1 }}>
          <CircularProgress size={18} />
        </Box>
      ) : recentAudit.length === 0 ? (
        <Typography variant="caption" color="text.secondary">
          No commands recorded for this mission yet.
        </Typography>
      ) : (
        <Table size="small" sx={{ "& .MuiTableCell-root": { fontSize: "0.72rem", py: 0.55 } }}>
          <TableHead>
            <TableRow>
              <TableCell>Time</TableCell>
              <TableCell>Command</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Transition</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {recentAudit.map((entry) => (
              <TableRow key={entry.command_id}>
                <TableCell>{formatTs(entry.requested_at)}</TableCell>
                <TableCell sx={{ textTransform: "uppercase" }}>{entry.command}</TableCell>
                <TableCell>
                  <Tooltip title={entry.message}>
                    <Chip
                      size="small"
                      label={entry.accepted ? "accepted" : "ignored"}
                      color={entry.accepted ? "success" : "default"}
                      variant={entry.accepted ? "filled" : "outlined"}
                    />
                  </Tooltip>
                </TableCell>
                <TableCell>{`${entry.state_before} -> ${entry.state_after}`}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Box>
  );
}
