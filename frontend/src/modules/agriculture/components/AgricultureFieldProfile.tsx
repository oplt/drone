import {
  Button,
  Card,
  CardContent,
  Grid,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";
import { usePatchAgricultureProfile } from "../hooks";
import type { AgricultureFieldProfile as FieldProfile } from "../types";

export function AgricultureFieldProfile({
  fieldId,
  value,
}: {
  fieldId: number;
  value: FieldProfile;
}) {
  const [draft, setDraft] = useState({
    crop_type: value.crop_type ?? "",
    variety: value.variety ?? "",
    season: value.season ?? "",
    planting_date: value.planting_date ?? "",
    growth_stage: value.growth_stage ?? "",
    row_direction_deg:
      value.row_direction_deg == null ? "" : String(value.row_direction_deg),
    expected_row_spacing_m:
      value.expected_row_spacing_m == null
        ? ""
        : String(value.expected_row_spacing_m),
    soil_type: value.soil_type ?? "",
    irrigation_method: value.irrigation_method ?? "",
    management_zone: value.management_zone ?? "",
    timezone: value.timezone,
    notes: value.notes ?? "",
  });
  const save = usePatchAgricultureProfile();
  const set = (key: keyof typeof draft, next: string) =>
    setDraft((current) => ({ ...current, [key]: next }));
  return (
    <Card
      component="section"
      aria-labelledby="agriculture-field-profile-heading"
      variant="outlined"
    >
      <CardContent>
        <Typography id="agriculture-field-profile-heading" variant="h6">
          Agriculture field profile
        </Typography>
        <Grid container spacing={1.5} sx={{ mt: 0.5 }}>
          {(
            [
              ["crop_type", "Crop"],
              ["variety", "Variety"],
              ["season", "Season"],
              ["planting_date", "Planting date"],
              ["growth_stage", "Growth stage"],
              ["row_direction_deg", "Row direction (°)"],
              ["expected_row_spacing_m", "Row spacing (m)"],
              ["soil_type", "Soil type"],
              ["irrigation_method", "Irrigation"],
              ["management_zone", "Management zone"],
              ["timezone", "Timezone"],
            ] as Array<[keyof typeof draft, string]>
          ).map(([key, label]) => (
            <Grid key={key} size={{ xs: 12, sm: 6, md: 4 }}>
              <TextField
                size="small"
                fullWidth
                label={label}
                type={key === "planting_date" ? "date" : "text"}
                slotProps={
                  key === "planting_date"
                    ? { inputLabel: { shrink: true } }
                    : undefined
                }
                value={draft[key]}
                onChange={(event) => set(key, event.target.value)}
              />
            </Grid>
          ))}
        </Grid>
        <TextField
          size="small"
          fullWidth
          multiline
          minRows={2}
          sx={{ mt: 1.5 }}
          label="Agronomist notes"
          value={draft.notes}
          onChange={(event) => set("notes", event.target.value)}
        />
        <Button
          sx={{ mt: 1.5, minHeight: 44 }}
          variant="contained"
          onClick={() =>
            save.mutate({
              fieldId,
              payload: {
                ...draft,
                planting_date: draft.planting_date || null,
                row_direction_deg: draft.row_direction_deg
                  ? Number(draft.row_direction_deg)
                  : null,
                expected_row_spacing_m: draft.expected_row_spacing_m
                  ? Number(draft.expected_row_spacing_m)
                  : null,
              },
            })
          }
          disabled={save.isPending}
        >
          {save.isPending ? "Saving…" : "Save field profile"}
        </Button>
      </CardContent>
    </Card>
  );
}
