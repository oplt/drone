import {
  Alert,
  Button,
  Chip,
  Divider,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import {
  useAgricultureAssistantRuns,
  useApproveAgricultureAssistantRun,
  useRunAgricultureAssistant,
} from "../hooks";

export function AgricultureGovernanceAssistantPanel({
  runId,
}: {
  runId: string;
}) {
  const runs = useAgricultureAssistantRuns(runId);
  const runAssistant = useRunAgricultureAssistant();
  const review = useApproveAgricultureAssistantRun();
  const [task, setTask] = useState("summary");
  const [question, setQuestion] = useState(
    "Summarize confirmed crop evidence and the next safe inspection steps.",
  );
  const latest = runs.data?.[0];
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1.25}>
        <div>
          <Typography variant="subtitle2">
            Evidence-grounded agriculture assistant
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Confirmed evidence + approved rules only. Raw frames, invented
            measurements and treatment rates are blocked.
          </Typography>
        </div>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <Select
            size="small"
            value={task}
            onChange={(event) => setTask(event.target.value)}
            inputProps={{ "aria-label": "Assistant task" }}
          >
            <MenuItem value="summary">Mission summary</MenuItem>
            <MenuItem value="comparison">Flight comparison</MenuItem>
            <MenuItem value="inspection_checklist">
              Inspection checklist
            </MenuItem>
            <MenuItem value="field_question">Field-data question</MenuItem>
          </Select>
          <TextField
            size="small"
            fullWidth
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            label="Question"
            inputProps={{ maxLength: 4000 }}
          />
          <Button
            variant="contained"
            size="small"
            onClick={() =>
              runAssistant.mutate({ runId, payload: { task, question } })
            }
            disabled={runAssistant.isPending || !question.trim()}
          >
            {runAssistant.isPending ? "Reviewing…" : "Ask"}
          </Button>
        </Stack>
        {runAssistant.error ? (
          <Alert severity="warning">
            Assistant request failed safely. Deterministic findings remain
            available.
          </Alert>
        ) : null}
        {latest ? (
          <Stack spacing={0.75}>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              <Chip
                size="small"
                label={latest.status}
                color={latest.status === "ok" ? "success" : "warning"}
              />
              <Chip
                size="small"
                label={
                  latest.abstained
                    ? "abstained"
                    : `confidence ${Math.round(latest.confidence * 100)}%`
                }
              />
              <Chip
                size="small"
                label="human approval required"
                color="warning"
              />
              <Chip
                size="small"
                variant="outlined"
                label={`sources ${latest.source_ids.length}`}
              />
            </Stack>
            <Typography variant="body2">{latest.output.summary}</Typography>
            {latest.output.key_points?.map((item) => (
              <Typography variant="caption" key={item}>
                • {item}
              </Typography>
            ))}
            <Typography variant="caption" color="text.secondary">
              Deterministic findings: {latest.deterministic_rules.length} ·
              prompt {latest.prompt_version} · context{" "}
              {latest.context_checksum.slice(0, 12)}
            </Typography>
            {latest.citations.length ? (
              <Typography variant="caption">
                Citations:{" "}
                {latest.citations
                  .map((item) => String(item.source_id))
                  .join(", ")}
              </Typography>
            ) : null}
            {latest.output.limitations?.map((item) => (
              <Typography variant="caption" color="text.secondary" key={item}>
                Limit: {item}
              </Typography>
            ))}
            <Divider />
            <Stack direction="row" spacing={0.5} alignItems="center">
              <Chip
                size="small"
                label={`review ${latest.review_status}`}
                color={
                  latest.review_status === "approved"
                    ? "success"
                    : latest.review_status === "rejected"
                      ? "error"
                      : "warning"
                }
              />
              {latest.review_status === "pending" ? (
                <>
                  <Button
                    size="small"
                    color="success"
                    onClick={() =>
                      review.mutate({
                        id: latest.id,
                        runId,
                        status: "approved",
                      })
                    }
                  >
                    Approve
                  </Button>
                  <Button
                    size="small"
                    color="error"
                    onClick={() =>
                      review.mutate({
                        id: latest.id,
                        runId,
                        status: "rejected",
                      })
                    }
                  >
                    Reject
                  </Button>
                </>
              ) : null}
            </Stack>
          </Stack>
        ) : (
          <Alert severity="info">
            Ask after post-flight analysis has produced confirmed evidence.
          </Alert>
        )}
      </Stack>
    </Paper>
  );
}
