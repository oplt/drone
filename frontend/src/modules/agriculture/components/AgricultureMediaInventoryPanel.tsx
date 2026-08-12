import { Alert, Button, Chip, CircularProgress, LinearProgress, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useAgricultureMediaInventory, useReconcileAgricultureMedia, useRevokeAgricultureMedia, useRestoreAgricultureMedia, useBackupAgricultureMedia } from "../hooks";
import { ReasonConfirmDialog } from "./ReasonConfirmDialog";

export function AgricultureMediaInventoryPanel({ flightId }: { flightId: string | null }) {
  const inventory = useAgricultureMediaInventory(flightId);
  const reconcile = useReconcileAgricultureMedia();
  const revoke = useRevokeAgricultureMedia();
  const restore = useRestoreAgricultureMedia();
  const backup = useBackupAgricultureMedia();
  const [lifecycleAction, setLifecycleAction] = useState<{ kind: "backup" | "revoke" | "restore"; mediaId: string } | null>(null);
  if (inventory.isLoading) return <Stack direction="row" spacing={1} role="status"><CircularProgress size={16} /><Typography variant="caption">Checking capture inventory…</Typography></Stack>;
  if (inventory.isError) return <Alert severity="warning">Capture inventory unavailable. Retry before launching analysis.</Alert>;
  const data = inventory.data;
  if (!data) return null;
  const missing = data.missing_manifest_ids ?? [];
  const active = data.active_upload_ids ?? data.uploads.filter((item) => item.status === "uploading").map((item) => String(item.id ?? ""));
  const storageMissing = data.storage_missing_media_ids ?? [];
  const quarantinedIds = data.quarantined_upload_ids ?? [];
  const exceptions = data.open_exception_count ?? 0;
  const incomplete = missing.length > 0 || active.length > 0 || storageMissing.length > 0 || quarantinedIds.length > 0 || exceptions > 0;
  const quarantined = data.uploads.filter((item) => item.status === "quarantined");
  return (
    <Stack component="section" aria-labelledby="agriculture-media-inventory-title" spacing={1} sx={{ p: 1.5, border: 1, borderColor: "divider", borderRadius: 1 }}>
      <Typography id="agriculture-media-inventory-title" variant="subtitle2">Capture inventory</Typography>
      <Button size="small" variant="outlined" onClick={() => flightId && reconcile.mutate(flightId)} disabled={!flightId || reconcile.isPending}> {reconcile.isPending ? "Reconciling…" : "Reconcile storage and captures"}</Button>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Chip size="small" label={`Registered ${data.registered}`} />
        <Chip size="small" label={`Expected ${data.expected}`} />
        <Chip size="small" label={`Frames processed ${data.processed_frame_count ?? 0}`} />
        <Chip size="small" label={`${Math.round(((data.storage_usage_bytes ?? 0) / Math.max(1, data.storage_quota_bytes ?? 1)) * 100)}% storage used`} />
        <Chip size="small" color={data.ready_for_processing ? "success" : "warning"} label={data.ready_for_processing ? "Ready for processing" : "Validation pending"} />
      </Stack>
      {incomplete ? <Alert severity="warning">Missing or active uploads must be resolved before analysis.</Alert> : <Alert severity="success">All registered media passed upload reconciliation.</Alert>}
      {quarantined.length ? (
        <Alert severity="error">
          {quarantined.length} upload(s) are quarantined. Resolve the recorded
          checksum or content validation reason before retrying; quarantined
          bytes are excluded from processing.
        </Alert>
      ) : null}
      {exceptions ? <Alert severity="error">{exceptions} reconciliation exception(s) require attention before processing.</Alert> : null}
      {storageMissing.length ? <Alert severity="error">{storageMissing.length} registered media object(s) are missing from storage.</Alert> : null}
      {reconcile.isError ? <Alert severity="error">Reconciliation failed. Retry when storage is reachable.</Alert> : null}
      {active.length ? <LinearProgress variant="indeterminate" aria-label="Media uploads still active" /> : null}
      {data.uploads.length ? (
        <Stack component="ul" aria-label="Upload reconciliation details" spacing={0.5} sx={{ m: 0, pl: 2.5 }}>
          {data.uploads.map((item) => (
            <Typography component="li" variant="caption" key={String(item.id ?? item.upload_id)}>
              {String(item.id ?? item.upload_id ?? "upload")} · {String(item.status ?? "unknown")}
              {item.security_reason ? ` · ${String(item.security_reason)}` : ""}
            </Typography>
          ))}
        </Stack>
      ) : null}
      {data.manifests.length ? (
        <Stack component="ul" aria-label="Media artifact security and retention" spacing={0.75} sx={{ m: 0, pl: 2.5 }}>
          {data.manifests.map((item) => {
            const retained = item.retention_status === "active";
            return (
              <Stack component="li" key={item.id} direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
                <Typography variant="caption" sx={{ flex: 1 }}>
                  {item.source_kind} · {item.checksum.slice(0, 12)}… · {item.security_status} · {item.retention_status}
                  {item.retention_expires_at ? ` · expires ${new Date(item.retention_expires_at).toLocaleDateString()}` : ""}
                </Typography>
                <Stack direction="row" spacing={0.5}>
                  <Button size="small" onClick={() => setLifecycleAction({ kind: "backup", mediaId: item.id })} disabled={backup.isPending || !item.storage_present}>Backup</Button>
                  {retained ? <Button size="small" color="warning" onClick={() => setLifecycleAction({ kind: "revoke", mediaId: item.id })} disabled={revoke.isPending}>Revoke</Button> : <Button size="small" color="success" onClick={() => setLifecycleAction({ kind: "restore", mediaId: item.id })} disabled={restore.isPending}>Restore</Button>}
                </Stack>
              </Stack>
            );
          })}
        </Stack>
      ) : null}
      <ReasonConfirmDialog
        open={Boolean(lifecycleAction)}
        title={`${lifecycleAction?.kind === "backup" ? "Create verified backup" : lifecycleAction?.kind === "revoke" ? "Revoke media access" : "Restore media access"}`}
        confirmLabel={lifecycleAction?.kind === "backup" ? "Create backup" : lifecycleAction?.kind === "revoke" ? "Revoke access" : "Restore access"}
        description={lifecycleAction?.kind === "revoke" ? "This removes access to the retained artifact until it is explicitly restored." : "This lifecycle change is recorded in the audit history."}
        irreversible={lifecycleAction?.kind === "revoke"}
        pending={backup.isPending || revoke.isPending || restore.isPending}
        onClose={() => setLifecycleAction(null)}
        onConfirm={(reason) => {
          if (!lifecycleAction) return;
          const mutation = lifecycleAction.kind === "backup" ? backup : lifecycleAction.kind === "revoke" ? revoke : restore;
          mutation.mutate({ mediaId: lifecycleAction.mediaId, reason }, { onSuccess: () => setLifecycleAction(null) });
        }}
      />
      {revoke.isError || restore.isError || backup.isError ? <Alert severity="error">Artifact lifecycle action failed. Check storage availability, permissions, and retention state.</Alert> : null}
    </Stack>
  );
}
