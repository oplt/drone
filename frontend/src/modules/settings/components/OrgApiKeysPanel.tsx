import { useCallback, useState } from "react";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import {
  createOrgApiKey,
  listOrgApiKeys,
  revokeOrgApiKey,
  type OrgApiKey,
} from "../api/orgApiKeysApi";

const ORG_API_KEYS_QUERY_KEY = ["org-api-keys"] as const;

type OrgApiKeysPanelProps = {
  token?: string | null;
  hasOrg?: boolean;
};

export function OrgApiKeysPanel({ token, hasOrg = true }: OrgApiKeysPanelProps) {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [keyName, setKeyName] = useState("Property patrol webhook");
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const keysQuery = useQuery({
    queryKey: ORG_API_KEYS_QUERY_KEY,
    enabled: hasOrg,
    queryFn: () => listOrgApiKeys(token),
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createOrgApiKey(name, token),
    onSuccess: (created) => {
      setCreatedKey(created.raw_key);
      setCreateOpen(false);
      setKeyName("Property patrol webhook");
      void queryClient.invalidateQueries({ queryKey: ORG_API_KEYS_QUERY_KEY });
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Failed to create API key");
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (keyId: number) => revokeOrgApiKey(keyId, token),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ORG_API_KEYS_QUERY_KEY });
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Failed to revoke API key");
    },
  });

  const handleCopy = useCallback(async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      setError("Could not copy to clipboard");
    }
  }, []);

  if (!hasOrg) {
    return (
      <Alert severity="info">
        Organisation API keys are available after your account is linked to an organisation.
      </Alert>
    );
  }

  const keys = keysQuery.data ?? [];

  return (
    <Stack spacing={2}>
      <Typography variant="body2" color="text.secondary">
        Create keys for external integrations such as Property Patrol event-trigger webhooks. Use{" "}
        <code>Authorization: Bearer sk-…</code> on POST requests.
      </Typography>

      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {createdKey && (
        <Alert
          severity="success"
          onClose={() => setCreatedKey(null)}
          action={
            <Tooltip title="Copy API key">
              <IconButton
                color="inherit"
                size="small"
                aria-label="Copy API key"
                onClick={() => void handleCopy(createdKey)}
              >
                <ContentCopyIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          }
        >
          <Typography variant="body2" sx={{ mb: 0.5 }}>
            Copy this key now — it will not be shown again.
          </Typography>
          <Box
            component="code"
            sx={{
              display: "block",
              wordBreak: "break-all",
              fontSize: "0.85rem",
            }}
          >
            {createdKey}
          </Box>
        </Alert>
      )}

      <Box>
        <ActionIconButton variant="add" title="Create API key" onClick={() => setCreateOpen(true)} />
      </Box>

      {keysQuery.isLoading ? (
        <Typography variant="body2" color="text.secondary">
          Loading API keys…
        </Typography>
      ) : keys.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No active API keys yet.
        </Typography>
      ) : (
        <Stack spacing={1}>
          {keys.map((key: OrgApiKey) => (
            <Box
              key={key.id}
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 1,
                p: 1,
                border: 1,
                borderColor: "divider",
                borderRadius: 1,
              }}
            >
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="body2" fontWeight={600} noWrap>
                  {key.name}
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  sk-{key.key_prefix}_••••••••
                  {key.last_used_at
                    ? ` · last used ${new Date(key.last_used_at).toLocaleString()}`
                    : " · never used"}
                </Typography>
              </Box>
              <ActionIconButton
                variant="delete"
                title="Revoke API key"
                disabled={revokeMutation.isPending}
                onClick={() => revokeMutation.mutate(key.id)}
              />
            </Box>
          ))}
        </Stack>
      )}

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Create API key</DialogTitle>
        <DialogContent>
          <TextField
            variant="filled"
            autoFocus
            fullWidth
            margin="dense"
            label="Key name"
            value={keyName}
            onChange={(e) => setKeyName(e.target.value)}
            placeholder="Property patrol webhook"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!keyName.trim() || createMutation.isPending}
            onClick={() => createMutation.mutate(keyName.trim())}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
