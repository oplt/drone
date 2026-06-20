import { Slider, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";

export function WarehouseLayerBudgetSlider({
  label,
  value,
  onCommit,
}: {
  label: string;
  value: number;
  onCommit: (value: number) => void;
}) {
  const [draftValue, setDraftValue] = useState(value);

  useEffect(() => {
    setDraftValue(value);
  }, [value]);

  return (
    <Stack direction="row" spacing={1} alignItems="center">
      <Typography variant="caption" sx={{ minWidth: 160 }}>
        {label}
      </Typography>
      <Slider
        aria-label={`Maximum points for ${label}`}
        size="small"
        sx={{ flex: 1 }}
        min={10_000}
        max={250_000}
        step={10_000}
        value={Math.min(draftValue, 250_000)}
        onChange={(_event, nextValue) => setDraftValue(Number(nextValue))}
        onChangeCommitted={(_event, nextValue) => {
          const committedValue = Number(nextValue);
          setDraftValue(committedValue);
          onCommit(committedValue);
        }}
      />
      <Typography variant="caption" sx={{ minWidth: 72 }}>
        {(draftValue / 1000).toFixed(0)}k
      </Typography>
    </Stack>
  );
}
