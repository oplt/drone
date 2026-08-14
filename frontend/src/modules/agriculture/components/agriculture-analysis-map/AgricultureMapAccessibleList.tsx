import { Button, Stack, Typography } from "@mui/material";
import { useRef } from "react";
import type { AgricultureAccessibleFeature } from "./types";

const ACCESSIBLE_LIST_LIMIT = 100;

function severityLabel(severity: number): string {
  if (severity >= 0.67) return "high";
  if (severity >= 0.34) return "medium";
  return "low";
}

export function AgricultureMapAccessibleList({
  features,
  selectedId,
  onSelect,
}: {
  features: AgricultureAccessibleFeature[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}) {
  const listRef = useRef<HTMLUListElement | null>(null);
  if (!features.length) return null;
  const visible = features.slice(0, ACCESSIBLE_LIST_LIMIT);
  const moveFocus = (index: number, direction: number) => {
    const buttons = listRef.current?.querySelectorAll<HTMLButtonElement>(
      "button[data-map-feature]",
    );
    if (!buttons?.length) return;
    buttons[(index + direction + buttons.length) % buttons.length]?.focus();
  };
  return (
    <details>
      <Typography component="summary" variant="body2" sx={{ minHeight: 44, py: 1 }}>
        Review mapped features without using the map ({features.length})
      </Typography>
      <Typography id="analysis-map-keyboard-help" variant="caption" color="text.secondary">
        Use Tab to enter the list. Use Arrow keys to move between mapped
        features and Enter to open the selected review.
      </Typography>
      <Stack
        component="ul"
        ref={listRef}
        aria-label="Mapped feature review list"
        aria-describedby="analysis-map-keyboard-help"
        sx={{ listStyle: "none", p: 0, m: 0, maxHeight: 260, overflow: "auto" }}
      >
        {visible.map((feature, index) => (
          <li key={feature.id}>
            <Button
              disableRipple
              fullWidth
              data-map-feature
              variant={selectedId === feature.id ? "contained" : "text"}
              aria-current={selectedId === feature.id ? "true" : undefined}
              aria-label={`Select ${feature.label} ${feature.id}, ${severityLabel(feature.severity)} severity`}
              onClick={() => onSelect?.(feature.id)}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown" || event.key === "ArrowRight") {
                  event.preventDefault();
                  moveFocus(index, 1);
                }
                if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
                  event.preventDefault();
                  moveFocus(index, -1);
                }
              }}
              sx={{ justifyContent: "flex-start", minHeight: 44, textTransform: "none" }}
            >
              {feature.label} · {severityLabel(feature.severity)} severity · {feature.id}
            </Button>
          </li>
        ))}
      </Stack>
      {features.length > visible.length ? (
        <Typography variant="caption" color="text.secondary">
          Showing the first {visible.length} mapped features. Use the complete
          review list and filters below the map for all results.
        </Typography>
      ) : null}
    </details>
  );
}
