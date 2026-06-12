import { useEffect, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
} from "@mui/material";
import Grid from "@mui/material/Grid";

import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import {
  createLlmProfile,
  fetchLlmModels,
  fetchLlmProfileModels,
  updateLlmProfile,
  type LlmModel,
  type LlmProfile,
  type LlmProfileInput,
  type LlmProviderId,
} from "../api/settingsApi";
import { DEFAULT_AI_PROVIDERS, PROVIDER_IDS, PROVIDER_LABELS } from "../aiSettingsDefaults";
import { ApiError } from "../../../shared/api/apiError";


const emptyProfile = (): LlmProfileInput => ({
  name: "",
  provider: "ollama",
  api_base: "http://localhost:11434",
  model: "",
  enabled: true,
  api_key: "",
  timeout_seconds: 120,
  temperature: 0.2,
  max_tokens: 2048,
  context_window: 8192,
  streaming: true,
  vision_support: true,
  llama_connection_mode: "external_server",
  llama_command: "",
  llama_config: {
    binary_path: "",
    model_path: "",
    host: "127.0.0.1",
    port: 8080,
    api_base: "http://127.0.0.1:8080/v1",
    context_window: 8192,
    gpu_layers: 0,
    flash_attention: false,
    parallel_slots: 1,
    threads: 0,
    batch_size: 512,
    extra_allowed_args: [],
  },
});

function profileInput(profile: LlmProfile): LlmProfileInput {
  return {
    name: profile.name,
    provider: profile.provider,
    api_base: profile.api_base,
    model: profile.model,
    enabled: profile.enabled,
    api_key: "",
    has_api_key: profile.has_api_key,
    timeout_seconds: profile.timeout_seconds,
    temperature: profile.temperature,
    max_tokens: profile.max_tokens,
    context_window: profile.context_window,
    streaming: profile.streaming,
    vision_support: profile.vision_support,
    llama_connection_mode: profile.llama_connection_mode,
    llama_command: profile.llama_command,
    llama_config: profile.llama_config ?? emptyProfile().llama_config,
  };
}

type Props = {
  open: boolean;
  profile: LlmProfile | null;
  busy: boolean;
  onClose: () => void;
  onSaved: (profile: LlmProfile) => void;
  onBusyChange: (busy: boolean) => void;
};

function formatError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    return err.detail ?? err.message ?? fallback;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return fallback;
}

export function LlmProfileDialog({
  open,
  profile,
  busy,
  onClose,
  onSaved,
  onBusyChange,
}: Props) {
  const [draft, setDraft] = useState<LlmProfileInput>(emptyProfile());
  const [models, setModels] = useState<LlmModel[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(profile ? profileInput(profile) : emptyProfile());
    setModels([]);
    setError(null);
  }, [open, profile]);

  const fetchModels = async () => {
    onBusyChange(true);
    setError(null);
    try {
      const data = profile
        ? await fetchLlmProfileModels(profile.id)
        : await fetchLlmModels(draft.provider);
      setModels(data.models);
      if (!data.models.length) setError("No discovered models. Manual entry is available.");
    } catch (err) {
      setModels([]);
      setError(formatError(err, "Model discovery failed."));
    } finally {
      onBusyChange(false);
    }
  };

  const saveProfile = async () => {
    if (!draft.name.trim()) {
      setError("Display name is required.");
      return;
    }
    if (
      draft.provider === "huggingface" &&
      !draft.api_key?.trim() &&
      !draft.has_api_key
    ) {
      setError("HuggingFace token is required.");
      return;
    }
    if (draft.provider === "huggingface" && !draft.model.trim()) {
      setError("HuggingFace model id is required.");
      return;
    }
    onBusyChange(true);
    setError(null);
    try {
      const payload = normalizeDraft(draft);
      const saved = profile
        ? await updateLlmProfile(profile.id, payload)
        : await createLlmProfile(payload);
      onSaved(saved);
      onClose();
    } catch (err) {
      setError(formatError(err, "Failed to save LLM profile."));
    } finally {
      onBusyChange(false);
    }
  };

  const isLlama = draft.provider === "llama_cpp";
  const isHuggingFace = draft.provider === "huggingface";
  const apiKeyLabel = isHuggingFace ? "HuggingFace token" : "API key";
  const modelHelperText = isHuggingFace
    ? "Use a HuggingFace model id, e.g. Qwen/Qwen2.5-7B-Instruct"
    : undefined;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{profile ? "Edit LLM Profile" : "Add LLM Profile"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && (
            <Alert severity="warning" onClose={() => setError(null)}>
              {error}
            </Alert>
          )}
          <TextField fullWidth label="Display name" value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
          <TextField
            select
            fullWidth
            label="Provider"
            value={draft.provider}
            onChange={(event) => {
              const provider = event.target.value as LlmProviderId;
              setDraft({
                ...draft,
                provider,
                api_base: DEFAULT_AI_PROVIDERS[provider].api_base,
              });
              setModels([]);
            }}
          >
            {PROVIDER_IDS.map((provider) => (
              <MenuItem key={provider} value={provider}>
                {PROVIDER_LABELS[provider]}
              </MenuItem>
            ))}
          </TextField>

          {isLlama && (
            <TextField
              fullWidth
              multiline
              minRows={6}
              label="llama-server command"
              value={draft.llama_command}
              onChange={(event) => setDraft({ ...draft, llama_command: event.target.value })}
              helperText="Used to start llama-server automatically before AI calls when the server is not reachable."
            />
          )}

          <TextField fullWidth label="Server URL" value={draft.api_base} onChange={(event) => setDraft({ ...draft, api_base: event.target.value })} />
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField
              select={models.length > 0}
              fullWidth
              label="Model"
              helperText={modelHelperText}
              value={draft.model}
              onChange={(event) => setDraft({ ...draft, model: event.target.value })}
            >
              {models.map((model) => (
                <MenuItem key={model.id} value={model.id}>
                  {model.name}
                </MenuItem>
              ))}
            </TextField>
            <ActionIconButton variant="refresh" title="Fetch models" loading={busy} disabled={busy} onClick={fetchModels} />
          </Stack>

          {!["ollama", "llama_cpp"].includes(draft.provider) && (
            <TextField
              fullWidth
              type="password"
              label={apiKeyLabel}
              placeholder={draft.has_api_key ? "********" : ""}
              value={draft.api_key ?? ""}
              onChange={(event) => setDraft({ ...draft, api_key: event.target.value })}
              helperText={
                isHuggingFace
                  ? "Generate a token at huggingface.co/settings/tokens with inference access."
                  : undefined
              }
            />
          )}

          <Accordion>
            <AccordionSummary>Advanced settings</AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid size={{ xs: 6 }}>
                  <TextField fullWidth type="number" label="Temperature" value={draft.temperature} onChange={(event) => setDraft({ ...draft, temperature: Number(event.target.value) })} />
                </Grid>
                <Grid size={{ xs: 6 }}>
                  <TextField fullWidth type="number" label="Max tokens" value={draft.max_tokens} onChange={(event) => setDraft({ ...draft, max_tokens: Number(event.target.value) })} />
                </Grid>
                <Grid size={{ xs: 6 }}>
                  <TextField fullWidth type="number" label="Context window" value={draft.context_window} onChange={(event) => setDraft({ ...draft, context_window: Number(event.target.value) })} />
                </Grid>
                <Grid size={{ xs: 6 }}>
                  <TextField fullWidth type="number" label="Timeout seconds" value={draft.timeout_seconds} onChange={(event) => setDraft({ ...draft, timeout_seconds: Number(event.target.value) })} />
                </Grid>
                <Grid size={{ xs: 6 }}>
                  <FormControlLabel control={<Switch checked={draft.streaming} onChange={(event) => setDraft({ ...draft, streaming: event.target.checked })} />} label="Streaming" />
                </Grid>
                <Grid size={{ xs: 6 }}>
                  <FormControlLabel control={<Switch checked={draft.vision_support} onChange={(event) => setDraft({ ...draft, vision_support: event.target.checked })} />} label="Vision" />
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={busy} onClick={saveProfile}>
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function normalizeDraft(draft: LlmProfileInput): LlmProfileInput {
  const payload: LlmProfileInput = {
    ...draft,
    has_api_key: draft.has_api_key ?? false,
  };
  if (payload.provider !== "llama_cpp") {
    return { ...payload, llama_command: "", llama_config: emptyProfile().llama_config };
  }
  if (!payload.llama_command.trim()) {
    return {
      ...payload,
      llama_connection_mode: "external_server",
      llama_command: "",
      llama_config: emptyProfile().llama_config,
    };
  }
  return payload;
}
