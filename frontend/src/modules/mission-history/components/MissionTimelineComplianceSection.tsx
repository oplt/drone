import { useId, useState } from "react";
import { Box, Chip, Collapse, IconButton, Paper, Stack, Typography } from "@mui/material";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";

type ComplianceData = {
  remote_id_status?: string;
  laanc_auth_number?: string;
  preflight_ack_at?: string;
  laanc_auth_expires?: string;
  notes?: string;
};

export function MissionTimelineComplianceSection({ data }: { data: ComplianceData }) {
  const [open, setOpen] = useState(false);
  const contentId = useId();
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1} justifyContent="space-between">
        <Stack direction="row" alignItems="center" spacing={1}>
          <Typography fontWeight={600}>Compliance</Typography>
          <Chip
            label={data.remote_id_status ?? "unknown"}
            size="small"
            color={data.remote_id_status === "broadcast" ? "success" : "default"}
          />
          {data.laanc_auth_number && (
            <Chip label={`LAANC: ${data.laanc_auth_number}`} size="small" variant="outlined" />
          )}
        </Stack>
        <IconButton
          size="small"
          aria-label={open ? "Collapse compliance details" : "Expand compliance details"}
          aria-expanded={open}
          aria-controls={contentId}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
        </IconButton>
      </Stack>
      <Collapse id={contentId} in={open}>
        <Stack spacing={1} sx={{ mt: 1.5 }}>
          {data.preflight_ack_at && (
            <Box>
              <Typography variant="caption" color="text.secondary">
                Preflight acknowledged
              </Typography>
              <Typography variant="body2">{new Date(data.preflight_ack_at).toLocaleString()}</Typography>
            </Box>
          )}
          {data.laanc_auth_expires && (
            <Box>
              <Typography variant="caption" color="text.secondary">
                LAANC expires
              </Typography>
              <Typography variant="body2">{new Date(data.laanc_auth_expires).toLocaleString()}</Typography>
            </Box>
          )}
          {data.notes && (
            <Box>
              <Typography variant="caption" color="text.secondary">
                Notes
              </Typography>
              <Typography variant="body2">{data.notes}</Typography>
            </Box>
          )}
        </Stack>
      </Collapse>
    </Paper>
  );
}
