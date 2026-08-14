import { useState } from "react";
import { CircularProgress, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { fetchMissionExportJob, startMissionExport } from "../api/missionHistoryApi";

export function MissionTimelineExportButton({ flightId }: { flightId: string }) {
  const [jobId, setJobId] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const { data: jobStatus, error: jobError } = useQuery({
    queryKey: ["export-job", flightId, jobId],
    queryFn: () => fetchMissionExportJob<{ status?: string; download_url?: string }>(flightId, String(jobId)),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "ready" || status === "failed" ? false : 3000;
    },
  });

  const handleExport = async () => {
    if (starting) return;
    setStarting(true);
    setStartError(null);
    try {
      const res = await startMissionExport<{ job_id: number }>(flightId);
      setJobId(res.job_id);
    } catch (error: unknown) {
      setStartError(error instanceof Error ? error.message : "Export could not be started.");
    } finally {
      setStarting(false);
    }
  };

  const exportError =
    startError ??
    (jobError instanceof Error ? jobError.message : jobError ? "Export status is unavailable." : null);
  if (exportError) {
    return (
      <Stack direction="row" alignItems="center" spacing={0.75} role="alert">
        <Typography variant="caption" color="error">
          {exportError}
        </Typography>
        <ActionIconButton
          variant="retry"
          title="Retry export"
          color="error"
          onClick={() => {
            setStartError(null);
            setJobId(null);
          }}
        />
      </Stack>
    );
  }

  if (jobStatus?.status === "ready" && jobStatus.download_url) {
    return (
      <ActionIconButton
        variant="download"
        title="Download ZIP"
        onClick={() => window.open(jobStatus.download_url, "_blank")}
      />
    );
  }

  if (jobId && jobStatus?.status === "failed") {
    return (
      <ActionIconButton
        variant="retry"
        title="Export failed: retry"
        color="error"
        onClick={() => setJobId(null)}
      />
    );
  }

  if (jobId && jobStatus && jobStatus.status !== "ready") {
    return (
      <Stack direction="row" alignItems="center" spacing={1}>
        <CircularProgress size={16} />
        <Typography variant="caption" color="text.secondary">
          Preparing export…
        </Typography>
      </Stack>
    );
  }

  return (
    <ActionIconButton
      variant="download"
      title="Export"
      loading={starting}
      disabled={starting}
      onClick={handleExport}
    />
  );
}
