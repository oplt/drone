import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getToken } from "../../../modules/session";
import { fieldsKeys } from "../../../app/config/queryKeys";
import {
  createMappingJob,
  createMappingJobFromUpload,
  deleteMappingJob,
  fetchMappingJob,
  listMappingJobs,
  startMappingJob,
  uploadMappingJobImages,
} from "../api/mappingJobsApi";
import type { MappingJobArtifacts, MappingJobRecord } from "../types";
import { FAST_3D_MAP_WEBODM_OPTIONS } from "../types";

const MESH_ARTIFACTS: MappingJobArtifacts = {
  orthomosaic: false,
  dsm: false,
  dtm: false,
  textured_mesh: true,
  point_cloud: false,
  xyz_tiles: false,
};

export function useMappingJobs(options?: {
  onJobReady?: (job: MappingJobRecord) => void;
  onJobFailed?: (job: MappingJobRecord) => void;
}) {
  const queryClient = useQueryClient();
  const [jobs, setJobs] = useState<MappingJobRecord[]>([]);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [status, setStatus] = useState<MappingJobRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshJob = useCallback(async (jobId: number) => {
    const token = getToken();
    if (!token) return null;
    const data = await fetchMappingJob(jobId, token);
    setStatus(data);
    setError(data.error ?? null);
    if (data.status === "ready") {
      void queryClient.invalidateQueries({ queryKey: fieldsKeys.tileset(data.field_id) });
      options?.onJobReady?.(data);
      setActiveJobId(null);
    } else if (data.status === "failed") {
      options?.onJobFailed?.(data);
      setActiveJobId(null);
    }
    return data;
  }, [options, queryClient]);

  const loadJobs = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setJobs(await listMappingJobs(token));
  }, []);

  useEffect(() => {
    if (activeJobId == null) return;
    let cancelled = false;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const next = await refreshJob(activeJobId);
        if (next?.status === "ready" || next?.status === "failed") return;
        attempt = Math.min(attempt + 1, 5);
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to refresh mapping progress");
          attempt = Math.min(attempt + 1, 5);
        }
      }
      if (!cancelled) {
        timer = setTimeout(() => void tick(), Math.min(30_000, 3_000 * 2 ** attempt));
      }
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [activeJobId, refreshJob]);

  const removeJob = useCallback(async (jobId: number) => {
    const token = getToken();
    if (!token) return;
    await deleteMappingJob(jobId, token);
    await loadJobs();
  }, [loadJobs]);

  const resumeJob = useCallback(async (jobId: number) => {
    const token = getToken();
    if (!token) return;
    await startMappingJob(jobId, token);
    setActiveJobId(jobId);
    await refreshJob(jobId);
  }, [refreshJob]);

  const createFromUpload = useCallback(
    async (files: File[], fieldName?: string) => {
      const token = getToken();
      if (!token) throw new Error("Not authenticated");
      setBusy(true);
      setError(null);
      setStatus(null);
      try {
        const created = await createMappingJobFromUpload(files, {
          field_name: fieldName,
          artifacts: MESH_ARTIFACTS,
          webodm_options: FAST_3D_MAP_WEBODM_OPTIONS,
        }, token);
        setStatus(created);
        if (created.status === "ready" || created.status === "failed") {
          setActiveJobId(null);
        } else {
          setActiveJobId(created.job_id);
        }
        await refreshJob(created.job_id);
        return created;
      } finally {
        setBusy(false);
      }
    },
    [refreshJob],
  );

  const createForField = useCallback(
    async (
      fieldId: number,
      inputMode: string,
      options: {
        files?: File[];
        syncSourceDir?: string;
      },
    ) => {
      const token = getToken();
      if (!token) throw new Error("Not authenticated");
      setBusy(true);
      setError(null);
      setStatus(null);
      try {
        const created = await createMappingJob(
          {
            field_id: fieldId,
            processor: "webodm",
            input_source: inputMode,
            drone_sync:
              inputMode === "drone_sync"
                ? { source_dir: options.syncSourceDir?.trim() || undefined, recursive: true }
                : undefined,
            start_immediately: inputMode === "drone_sync",
            artifacts: MESH_ARTIFACTS,
            webodm_options: FAST_3D_MAP_WEBODM_OPTIONS,
          },
          token,
        );
        const jobId = Number(created?.job_id);
        if (!Number.isFinite(jobId) || jobId <= 0) {
          throw new Error("Mapping job was created but no valid job id was returned.");
        }
        if (inputMode === "upload" && options.files?.length) {
          await uploadMappingJobImages(jobId, options.files, token);
          await startMappingJob(jobId, token);
        }
        setActiveJobId(jobId);
        await refreshJob(jobId);
        return jobId;
      } finally {
        setBusy(false);
      }
    },
    [refreshJob],
  );

  return {
    jobs,
    setJobs,
    loadJobs,
    activeJobId,
    setActiveJobId,
    status,
    setStatus,
    busy,
    error,
    setError,
    refreshJob,
    removeJob,
    resumeJob,
    createFromUpload,
    createForField,
  };
}
