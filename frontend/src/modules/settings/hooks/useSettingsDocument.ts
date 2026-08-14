import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { LlmProfile } from "../api/settingsApi";
import {
  fetchAppSettings,
  updateAppSettings,
  uploadAppSettingsFile,
} from "../api/settingsApi";
import {
  DEFAULT_SETTINGS_DOC,
  normalizeSettingsDoc,
  SETTINGS_QUERY_KEY,
} from "../settingsDefaults";
import type { SettingsDoc, SettingsSection } from "../settingsTypes";
import { validateSettingsDoc } from "../settingsValidation";
import { useSettingsDirtyFlag } from "./useSettingsDirtyFlag";

export function useSettingsDocument() {
  const queryClient = useQueryClient();
  const cachedSettings = queryClient.getQueryData<SettingsDoc>(SETTINGS_QUERY_KEY);
  const [err, setErr] = useState<string | null>(null);
  const [doc, setDoc] = useState<SettingsDoc>(cachedSettings ?? DEFAULT_SETTINGS_DOC);
  const { dirty, markDirty, markClean } = useSettingsDirtyFlag();

  const settingsQuery = useQuery<SettingsDoc>({
    queryKey: SETTINGS_QUERY_KEY,
    staleTime: 5 * 60_000,
    queryFn: async () => normalizeSettingsDoc(await fetchAppSettings<SettingsDoc>()),
  });
  const loading = settingsQuery.isLoading || settingsQuery.isFetching;

  useEffect(() => {
    if (!settingsQuery.data) return;
    setDoc(settingsQuery.data);
    markClean();
  }, [markClean, settingsQuery.data]);

  useEffect(() => {
    if (!settingsQuery.error) return;
    setErr(
      settingsQuery.error instanceof Error
        ? settingsQuery.error.message
        : "Failed to fetch settings",
    );
  }, [settingsQuery.error]);

  const settingsMutation = useMutation({
    mutationFn: async (payload: SettingsDoc) =>
      normalizeSettingsDoc(await updateAppSettings<SettingsDoc>(payload)),
    onSuccess: (saved) => {
      queryClient.setQueryData(SETTINGS_QUERY_KEY, saved);
      setDoc(saved);
      markClean();
    },
  });
  const saving = settingsMutation.isPending;

  const update = (section: SettingsSection, field: string, value: unknown) => {
    const currentValue = (doc[section] as Record<string, unknown>)[field];
    if (Object.is(currentValue, value)) return;
    setDoc((prev) => ({ ...prev, [section]: { ...prev[section], [field]: value } }));
    markDirty();
    if (err) setErr(null);
  };

  const persistAiProfiles = (profiles: LlmProfile[]) => {
    const applyProfiles = (prev: SettingsDoc): SettingsDoc => {
      const defaultProfile = profiles.find((profile) => profile.id === prev.ai.default_profile_id);
      return {
        ...prev,
        ai: {
          ...prev.ai,
          profiles,
          ...(defaultProfile
            ? {
                llm_provider: defaultProfile.provider,
                llm_api_base: defaultProfile.api_base,
                llm_model: defaultProfile.model,
                active_provider: defaultProfile.provider,
              }
            : {}),
        },
      };
    };
    setDoc(applyProfiles);
    queryClient.setQueryData<SettingsDoc>(SETTINGS_QUERY_KEY, (current) =>
      applyProfiles(current ?? DEFAULT_SETTINGS_DOC),
    );
  };

  async function fetchSettings() {
    setErr(null);
    const result = await settingsQuery.refetch();
    if (result.error) {
      setErr(
        result.error instanceof Error
          ? result.error.message
          : "Failed to fetch settings",
      );
    }
  }

  async function saveSettings() {
    const validationError = validateSettingsDoc(doc);
    if (validationError) {
      setErr(validationError);
      return;
    }
    setErr(null);
    try {
      await settingsMutation.mutateAsync(doc);
    } catch (error: unknown) {
      setErr(error instanceof Error ? error.message : "Failed to save settings");
    }
  }

  function discardSettings() {
    const source = settingsQuery.data ?? cachedSettings ?? DEFAULT_SETTINGS_DOC;
    setDoc(source);
    markClean();
    setErr(null);
  }

  const handleFileUpload =
    (section: SettingsSection, field: string) =>
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      try {
        setErr(null);
        const formData = new FormData();
        formData.append("section", section);
        formData.append("field", field);
        formData.append("file", file);

        const payload = (await uploadAppSettingsFile(formData)) as { path?: string };
        if (typeof payload?.path !== "string" || !payload.path) {
          throw new Error("Upload succeeded but no path was returned.");
        }
        update(section, field, payload.path);
      } catch (error: unknown) {
        setErr(error instanceof Error ? error.message : "Failed to upload file.");
      } finally {
        event.target.value = "";
      }
    };

  return {
    doc,
    err,
    setErr,
    dirty,
    loading,
    saving,
    update,
    persistAiProfiles,
    fetchSettings,
    saveSettings,
    discardSettings,
    handleFileUpload,
  };
}
