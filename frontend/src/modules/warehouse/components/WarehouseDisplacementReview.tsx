import { useState } from "react";
import {
  Alert,
  Button,
  List,
  ListItem,
  ListItemText,
  Stack,
} from "@mui/material";
import {
  decideLayoutCandidate,
  reviewLayoutDisplacements,
  type LayoutCandidate,
} from "../api/warehouseLayoutApi";

export function WarehouseDisplacementReview({
  warehouseMapId,
  version,
  token,
}: {
  warehouseMapId: number;
  version: number;
  token?: string | null;
}) {
  const [items, setItems] = useState<LayoutCandidate[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const review = async () => {
    setBusy(true);
    setError(null);
    try {
      setItems(
        (await reviewLayoutDisplacements(warehouseMapId, version, token)).items,
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Displacement review failed.",
      );
    } finally {
      setBusy(false);
    }
  };
  const decide = async (
    candidate: LayoutCandidate,
    status: "accepted" | "rejected",
  ) => {
    const result = await decideLayoutCandidate(
      warehouseMapId,
      candidate.id,
      status,
      token,
    );
    setItems((current) =>
      current.map((item) => (item.id === candidate.id ? result.item : item)),
    );
  };
  const pending = items.filter((item) => item.status === "needs_review");
  return (
    <Stack spacing={1}>
      <Button variant="outlined" disabled={busy} onClick={() => void review()}>
        Review scan displacement
      </Button>
      {error && <Alert severity="error">{error}</Alert>}
      {items.length > 0 && pending.length === 0 && (
        <Alert severity="success">No unresolved scan displacement.</Alert>
      )}
      <List dense disablePadding aria-label="Displaced scan candidates">
        {pending.map((candidate) => (
          <ListItem
            key={candidate.id}
            secondaryAction={
              <Stack direction="row" spacing={0.5}>
                <Button
                  size="small"
                  onClick={() => void decide(candidate, "rejected")}
                >
                  Reject
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  onClick={() => void decide(candidate, "accepted")}
                >
                  Accept
                </Button>
              </Stack>
            }
          >
            <ListItemText
              primary={candidate.identity_key}
              secondary={`${(candidate.displacement_m ?? 0).toFixed(2)} m displacement · ${Math.round(candidate.confidence * 100)}% confidence`}
            />
          </ListItem>
        ))}
      </List>
    </Stack>
  );
}
