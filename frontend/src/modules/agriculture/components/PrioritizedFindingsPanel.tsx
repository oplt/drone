import {
  Button,
  Checkbox,
  Chip,
  Drawer,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { selectDetectionEvidence } from "../../video-analysis/evidenceSelection";
import {
  useAgricultureFindings,
  useCreateAgricultureFieldOutcome,
  useMergeAgricultureFindings,
  useReviewAgricultureObservation,
  useSplitAgricultureFinding,
} from "../hooks";
import type { AgricultureObservation } from "../types";
import type { RankedFinding } from "../types";
import {
  ANALYSIS_REVIEW_EVIDENCE,
  ANALYSIS_REVIEW_OPEN,
  readAnalysisReviewState,
  writeObservationSelection,
} from "../workflows/analysisReviewState";
import { AgricultureGeoJsonPreview } from "./AgricultureGeoJsonPreview";
import { ObservationReviewDrawer } from "./ObservationReviewDrawer";
import { BulkActionBar } from "../../../shared/ui/BulkActionBar";
import { FeatureState } from "../../../shared/ui/FeatureState";

const OUTCOME_OPTIONS = [
  "confirmed_present",
  "false_positive",
  "treated",
  "unresolved",
  "other",
] as const;

function factorSummary(factors: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(factors)) {
    if (!value || typeof value !== "object") continue;
    const factor = value as { factor?: number; contribution?: number };
    if (typeof factor.contribution === "number") {
      parts.push(`${key} ${factor.contribution.toFixed(2)}`);
    }
  }
  return parts.slice(0, 4).join(" · ") || "No factor breakdown";
}

function observationFromFinding(
  runId: string,
  finding: RankedFinding,
): AgricultureObservation {
  return {
    id: finding.observation_id,
    run_id: runId,
    flight_id: "",
    field_id: 0,
    observation_type: finding.observation_type || "finding",
    zone_kind: "observation",
    geometry_geojson: finding.geometry_geojson,
    georef_status: finding.georef_status || "unresolved",
    area_m2: finding.area_m2,
    severity: finding.severity,
    confidence: finding.confidence,
    uncertainty: {},
    provenance: finding.provenance,
    first_detected: null,
    last_detected: null,
    trend: "unknown",
    evidence_ids: (finding.evidence_ids || []).map(String),
    sensor_values: {},
    model_version: finding.model_version,
    review_state: finding.review_state || "unreviewed",
    review_label: null,
    review_note: null,
    assigned_to_user_id: finding.assigned_to_user_id,
    reviewed_at: null,
    merged_into_id: finding.merged_into_id,
    member_observation_ids: finding.member_observation_ids,
  };
}

export function PrioritizedFindingsPanel({
  runId,
  showHotspotMap = true,
}: {
  runId: string;
  showHotspotMap?: boolean;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const { observationId, reviewOpen, focusEvidence } =
    readAnalysisReviewState(searchParams);
  const findings = useAgricultureFindings(runId);
  const review = useReviewAgricultureObservation();
  const merge = useMergeAgricultureFindings();
  const split = useSplitAgricultureFinding();
  const outcome = useCreateAgricultureFieldOutcome();
  const [mergeSelection, setMergeSelection] = useState<string[]>([]);
  const [primaryId, setPrimaryId] = useState<string>("");
  const [outcomeStatus, setOutcomeStatus] = useState<(typeof OUTCOME_OPTIONS)[number]>("confirmed_present");
  const [outcomeNotes, setOutcomeNotes] = useState("");

  const items = findings.data?.items ?? [];
  const selected =
    items.find((item) => item.observation_id === observationId) ?? null;
  const hotspots = useMemo(
    () => findings.data?.hotspots ?? { type: "FeatureCollection", features: [] },
    [findings.data?.hotspots],
  );

  const selectObservation = (
    id: string,
    options?: { review?: typeof ANALYSIS_REVIEW_OPEN | typeof ANALYSIS_REVIEW_EVIDENCE | false },
  ) => {
    setSearchParams(
      writeObservationSelection(searchParams, id, options),
      { replace: true },
    );
  };

  const closeReviewDrawer = () => {
    setSearchParams(
      writeObservationSelection(searchParams, observationId, { review: false }),
      { replace: true },
    );
  };

  const jumpToEvidence = (item: RankedFinding) => {
    selectObservation(item.observation_id, { review: ANALYSIS_REVIEW_EVIDENCE });
    const evidenceId = item.evidence_ids?.[0];
    if (evidenceId) selectDetectionEvidence(String(evidenceId));
  };

  const toggleMergeMember = (id: string) => {
    setMergeSelection((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  };

  const statusColor = (status: RankedFinding["display_status"]) => {
    if (status === "shown") return "success" as const;
    if (status === "labeled_low_confidence") return "warning" as const;
    return "default" as const;
  };

  return (
    <Stack component="section" aria-labelledby="prioritized-findings-heading" spacing={1.5}>
      <div>
        <Typography id="prioritized-findings-heading" variant="h6">
          Prioritized findings
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Bounded work queue · rank score is not agronomic certainty
          {findings.data ? ` · policy ${findings.data.policy_version}` : ""}
        </Typography>
      </div>
      <FeatureState
        loading={findings.isLoading}
        error={findings.isError ? "Unable to load prioritized findings." : null}
        onRetry={() => void findings.refetch()}
        empty={
          !findings.isLoading && !items.length
            ? {
                title: "No ranked findings",
                description: "No ranked findings for this run yet.",
              }
            : undefined
        }
      >
      {showHotspotMap ? (
        <AgricultureGeoJsonPreview
          geojson={hotspots}
          selectedId={observationId}
          onSelect={(id) => selectObservation(id, { review: false })}
        />
      ) : null}
      <Stack spacing={1}>
        {items.map((item) => (
          <Stack
            key={item.finding_id}
            direction={{ xs: "column", md: "row" }}
            spacing={1}
            alignItems={{ md: "center" }}
            sx={{
              border: "1px solid",
              borderColor: observationId === item.observation_id ? "primary.main" : "divider",
              borderRadius: 1,
              p: 1,
            }}
          >
            <FormControlLabel
              control={
                <Checkbox
                  size="small"
                  checked={mergeSelection.includes(item.observation_id)}
                  onChange={() => toggleMergeMember(item.observation_id)}
                  inputProps={{ "aria-label": `Select finding ${item.rank} for merge` }}
                />
              }
              label={`#${item.rank}`}
            />
            <Chip size="small" label={(item.observation_type || "finding").replaceAll("_", " ")} />
            <Chip size="small" color={statusColor(item.display_status)} label={item.display_status.replaceAll("_", " ")} />
            <Typography variant="caption" sx={{ flex: 1 }}>
              Score {item.score.toFixed(3)} · {factorSummary(item.factors)}
            </Typography>
            <Button
              size="small"
              variant="contained"
              onClick={() => jumpToEvidence(item)}
              aria-label={`Jump to evidence for finding ${item.rank}`}
            >
              Jump to evidence
            </Button>
            <Button
              size="small"
              onClick={() => selectObservation(item.observation_id, { review: false })}
            >
              Select
            </Button>
            <Button
              size="small"
              color="success"
              disabled={review.isPending}
              onClick={() => review.mutate({ id: item.observation_id, payload: { status: "confirmed" } })}
            >
              Confirm
            </Button>
            <Button
              size="small"
              color="error"
              disabled={review.isPending}
              onClick={() => review.mutate({ id: item.observation_id, payload: { status: "rejected" } })}
            >
              Dismiss
            </Button>
          </Stack>
        ))}
      </Stack>
      {selected ? (
        <Stack spacing={1} sx={{ borderTop: "1px solid", borderColor: "divider", pt: 1 }}>
          <Typography variant="subtitle2">Selected finding {selected.observation_id}</Typography>
          <Typography variant="caption" color="text.secondary">
            Evidence: {(selected.evidence_ids || []).join(", ") || "none"} · model {selected.model_version || "n/a"}
          </Typography>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} flexWrap="wrap" useFlexGap>
            <TextField
              select
              size="small"
              label="Field outcome"
              value={outcomeStatus}
              onChange={(event) => setOutcomeStatus(event.target.value as (typeof OUTCOME_OPTIONS)[number])}
              sx={{ minWidth: 180 }}
            >
              {OUTCOME_OPTIONS.map((option) => (
                <MenuItem key={option} value={option}>
                  {option.replaceAll("_", " ")}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              size="small"
              label="Outcome notes"
              value={outcomeNotes}
              onChange={(event) => setOutcomeNotes(event.target.value)}
              sx={{ flex: 1 }}
            />
            <Button
              size="small"
              variant="outlined"
              disabled={outcome.isPending}
              onClick={() =>
                outcome.mutate({
                  runId,
                  payload: {
                    observation_id: selected.observation_id,
                    outcome_status: outcomeStatus,
                    notes: outcomeNotes || undefined,
                  },
                })
              }
            >
              Record outcome
            </Button>
            <Button
              size="small"
              variant="outlined"
              disabled={
                mergeSelection.length < 2 ||
                !mergeSelection.includes(selected.observation_id) ||
                split.isPending
              }
              onClick={() => {
                const evidence = (selected.evidence_ids || []).map(String);
                const mid = Math.max(1, Math.ceil(evidence.length / 2));
                split.mutate({
                  runId,
                  observationId: selected.observation_id,
                  payload: {
                    parts: [
                      {
                        geometry_geojson: selected.geometry_geojson,
                        evidence_ids: evidence.slice(0, mid),
                        severity: selected.severity,
                        confidence: selected.confidence,
                        area_m2: selected.area_m2 ?? undefined,
                      },
                      {
                        geometry_geojson: selected.geometry_geojson,
                        evidence_ids: evidence.slice(mid),
                        severity: selected.severity,
                        confidence: selected.confidence,
                        area_m2: selected.area_m2 ?? undefined,
                      },
                    ],
                    reason: "Split from prioritized findings queue",
                  },
                });
              }}
            >
              Split finding
            </Button>
            <Button
              size="small"
              onClick={() =>
                selectObservation(selected.observation_id, { review: ANALYSIS_REVIEW_OPEN })
              }
            >
              Open review drawer
            </Button>
          </Stack>
        </Stack>
      ) : null}
      <Drawer
        anchor="right"
        open={reviewOpen && Boolean(selected)}
        onClose={closeReviewDrawer}
        PaperProps={{ sx: { width: { xs: "100%", sm: 420 }, p: 2 } }}
      >
        {selected ? (
          <ObservationReviewDrawer
            observation={observationFromFinding(runId, selected)}
            focusEvidence={focusEvidence}
            onClose={closeReviewDrawer}
          />
        ) : null}
      </Drawer>
      <BulkActionBar selectedCount={mergeSelection.length} label="Findings bulk actions">
        <TextField
          select
          size="small"
          label="Merge primary"
          value={primaryId}
          onChange={(event) => setPrimaryId(event.target.value)}
          sx={{ minWidth: 200 }}
        >
          {items
            .filter((item) => mergeSelection.includes(item.observation_id))
            .map((item) => (
              <MenuItem key={item.observation_id} value={item.observation_id}>
                #{item.rank} {item.observation_type}
              </MenuItem>
            ))}
        </TextField>
        <Button
          size="small"
          variant="outlined"
          disabled={!primaryId || mergeSelection.filter((id) => id !== primaryId).length < 1 || merge.isPending}
          onClick={() =>
            merge.mutate({
              runId,
              payload: {
                primary_observation_id: primaryId,
                member_observation_ids: mergeSelection.filter((id) => id !== primaryId),
                reason: "Merged from prioritized findings queue",
              },
            }, {
              onSuccess: () => {
                setMergeSelection([]);
                setPrimaryId("");
              },
            })
          }
        >
          Merge selected into primary
        </Button>
      </BulkActionBar>
      </FeatureState>
    </Stack>
  );
}
