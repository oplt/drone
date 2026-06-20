import { useState } from "react";
import {
  Alert,
  Button,
  Collapse,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AutoAwesomeRoundedIcon from "@mui/icons-material/AutoAwesomeRounded";
import { useMissionAgent } from "../hooks/useMissionAgent";
import type { AgentRunRequest, MissionAgentId } from "../api/agentsApi";
import { AgentSummaryCard } from "./AgentSummaryCard";

type Props = {
  agentId: MissionAgentId;
  title?: string;
  placeholder?: string;
  basePayload?: Omit<AgentRunRequest, "question">;
};

export function AskAgentPanel({
  agentId,
  title = "Ask AI",
  placeholder = "Ask about this map, scan quality, or next steps…",
  basePayload,
}: Props) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const { run, loading, error, result } = useMissionAgent(agentId);

  const handleAsk = async () => {
    await run({
      phase: "on_demand",
      question: question.trim() || undefined,
      ...basePayload,
    });
  };

  return (
    <Stack spacing={1} sx={{ mt: 1 }}>
      <Button
        size="small"
        variant="outlined"
        startIcon={<AutoAwesomeRoundedIcon />}
        onClick={() => setOpen((value) => !value)}
      >
        {title}
      </Button>
      <Collapse in={open}>
        <Stack spacing={1} sx={{ pt: 1 }}>
          <Typography variant="caption" color="text.secondary">
            Advisory only — the agent does not control the drone.
          </Typography>
          <TextField
            size="small"
            multiline
            minRows={2}
            placeholder={placeholder}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <Button
            size="small"
            variant="contained"
            disabled={loading}
            onClick={() => void handleAsk()}
          >
            {loading ? "Thinking…" : "Ask"}
          </Button>
          {error ? <Alert severity="warning">{error}</Alert> : null}
          <AgentSummaryCard result={result} loading={loading} />
        </Stack>
      </Collapse>
    </Stack>
  );
}
