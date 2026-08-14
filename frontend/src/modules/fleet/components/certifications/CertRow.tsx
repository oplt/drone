import BadgeRoundedIcon from "@mui/icons-material/BadgeRounded";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import type { CertItem } from "../../types";

type CertRowProps = {
  cert: CertItem;
};

export function CertRow({ cert }: CertRowProps) {
  const expiry = cert.expires_at
    ? new Date(cert.expires_at).toLocaleDateString()
    : "No expiry";

  return (
    <Paper
      variant="outlined"
      sx={{ p: 2, borderRadius: 3, display: "flex", alignItems: "center", gap: 2 }}
    >
      <Box sx={{ flexGrow: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Chip label={cert.cert_type.replace(/_/g, " ")} size="small" variant="outlined" />
          <Typography variant="body1" fontWeight={600} noWrap>
            {cert.cert_number}
          </Typography>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Issued {new Date(cert.issued_at).toLocaleDateString()} · Expires {expiry}
          {cert.issuing_authority ? ` · ${cert.issuing_authority}` : ""}
        </Typography>
      </Box>
      {cert.document_url && (
        <Tooltip title="View document">
          <IconButton
            size="small"
            component="a"
            href={cert.document_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            <BadgeRoundedIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}
    </Paper>
  );
}
