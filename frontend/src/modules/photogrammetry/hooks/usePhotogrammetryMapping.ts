import { useCallback, useEffect, useRef, useState } from "react";
import { getToken } from "../../../modules/session";
import { useMappingJobs } from "./useMappingJobs";
import type { FieldOutDTO, LonLat } from "../../fields";

export function usePhotogrammetryMapping({
  selectedFieldId,
  setSelectedFieldId,
  fieldBorder,
  fieldName,
  ensureFieldForMapping,
  onJobReady,
  addError,
}: {
  selectedFieldId: number | null;
  setSelectedFieldId: (id: number | null) => void;
  fieldBorder: LonLat[] | null;
  fieldName: string;
  ensureFieldForMapping: (options?: { announce?: boolean }) => Promise<FieldOutDTO>;
  onJobReady: () => void;
  addError: (message: string) => void;
}) {
  const suppressFieldSelectionResetRef = useRef(false);
  const [mappingInputMode, setMappingInputMode] = useState<"upload" | "drone_sync">(
    "upload"
  );
  const [mappingInputFiles, setMappingInputFiles] = useState<File[]>([]);
  const [mappingSyncSourceDir, setMappingSyncSourceDir] = useState("");

  const mappingJobs = useMappingJobs({
    onJobReady: () => onJobReady(),
    onJobFailed: () => {},
  });

  useEffect(() => {
    void mappingJobs.loadJobs();
  }, [mappingJobs.loadJobs]);

  useEffect(() => {
    if (suppressFieldSelectionResetRef.current) {
      suppressFieldSelectionResetRef.current = false;
      return;
    }
    mappingJobs.setError(null);
    mappingJobs.setStatus(null);
    mappingJobs.setActiveJobId(null);
  }, [
    selectedFieldId,
    mappingJobs.setError,
    mappingJobs.setStatus,
    mappingJobs.setActiveJobId,
  ]);

  const mappingJobRunning = mappingJobs.activeJobId != null;
  const mappingWillAutoSaveField =
    selectedFieldId == null &&
    Boolean(fieldBorder && fieldBorder.length >= 3 && fieldName.trim());
  const mappingWillInferFieldFromUpload =
    mappingInputMode === "upload" &&
    selectedFieldId == null &&
    !mappingWillAutoSaveField;
  const mappingFieldReady =
    mappingInputMode === "upload"
      ? true
      : selectedFieldId != null || mappingWillAutoSaveField;

  const create3DFieldMap = useCallback(async () => {
    if (!getToken()) {
      mappingJobs.setError("Not authenticated");
      return;
    }
    if (mappingInputMode === "upload" && mappingInputFiles.length === 0) {
      mappingJobs.setError(
        "Select mapping images before starting upload-based processing."
      );
      return;
    }

    try {
      if (mappingInputMode === "upload" && mappingWillInferFieldFromUpload) {
        const trimmedFieldName = fieldName.trim();
        const created = await mappingJobs.createFromUpload(
          mappingInputFiles,
          trimmedFieldName && trimmedFieldName !== "Field A"
            ? trimmedFieldName
            : undefined
        );
        suppressFieldSelectionResetRef.current = true;
        setSelectedFieldId(created.field_id);
        return;
      }

      let fieldId = selectedFieldId;
      if (fieldId == null) {
        const savedField = await ensureFieldForMapping({ announce: false });
        fieldId = savedField.id;
      }
      if (fieldId == null) {
        throw new Error("Select or save a field before starting mapping.");
      }

      await mappingJobs.createForField(fieldId, mappingInputMode, {
        files: mappingInputMode === "upload" ? mappingInputFiles : undefined,
        syncSourceDir: mappingSyncSourceDir,
      });
    } catch (e: unknown) {
      mappingJobs.setError(
        e instanceof Error ? e.message : "Failed to create 3D field map"
      );
    }
  }, [
    ensureFieldForMapping,
    fieldName,
    mappingInputFiles,
    mappingInputMode,
    mappingJobs,
    mappingSyncSourceDir,
    mappingWillInferFieldFromUpload,
    selectedFieldId,
    setSelectedFieldId,
  ]);

  const handleDeleteJob = useCallback(
    async (jobId: number) => {
      if (!getToken()) {
        addError("Not authenticated");
        return;
      }
      if (!window.confirm(`Are you sure you want to delete job #${jobId}?`)) {
        return;
      }
      try {
        await mappingJobs.removeJob(jobId);
      } catch (e: unknown) {
        addError(e instanceof Error ? e.message : `Failed to delete job #${jobId}`);
      }
    },
    [addError, mappingJobs]
  );

  const handleResumeJob = useCallback(
    async (jobId: number) => {
      if (!getToken()) {
        addError("Not authenticated");
        return;
      }
      try {
        await mappingJobs.resumeJob(jobId);
        await mappingJobs.loadJobs();
      } catch (e: unknown) {
        addError(e instanceof Error ? e.message : `Failed to resume job #${jobId}`);
      }
    },
    [addError, mappingJobs]
  );

  return {
    mappingInputMode,
    setMappingInputMode,
    mappingInputFiles,
    setMappingInputFiles,
    mappingSyncSourceDir,
    setMappingSyncSourceDir,
    mappingJobRunning,
    mappingWillAutoSaveField,
    mappingWillInferFieldFromUpload,
    mappingFieldReady,
    create3DFieldMap,
    handleDeleteJob,
    handleResumeJob,
    jobs: mappingJobs.jobs,
    jobStatus: mappingJobs.status,
    busy: mappingJobs.busy,
    error: mappingJobs.error,
  };
}
