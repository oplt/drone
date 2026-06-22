import { Box, Stack } from "@mui/material";
import { FieldBorderPanel } from "./FieldBorderPanel";
import { SavedFieldsPanel } from "./SavedFieldsPanel";
import type { BorderMetrics, FieldFeature, LonLat } from "../types";

export function WorkflowFieldsBlock({
  fields,
  selectedFieldId,
  selectedField,
  loadingFields,
  deletingField,
  onSelectField,
  onRefreshFields,
  onFocusSelected,
  onDeleteSelected,
  fieldName,
  fieldBorder,
  metrics,
  savingField,
  onFieldNameChange,
  onSaveOrUpdate,
  onClearBorder,
  onNewField,
  compact = false,
}: {
  fields: FieldFeature[];
  selectedFieldId: number | null;
  selectedField: FieldFeature | null;
  loadingFields: boolean;
  deletingField: boolean;
  onSelectField: (fieldId: number | null) => void;
  onRefreshFields: () => void;
  onFocusSelected: () => void;
  onDeleteSelected: () => void;
  fieldName: string;
  fieldBorder: LonLat[] | null;
  metrics: BorderMetrics | null;
  savingField: boolean;
  onFieldNameChange: (name: string) => void;
  onSaveOrUpdate: () => void;
  onClearBorder: () => void;
  onNewField: () => void;
  compact?: boolean;
}) {
  return (
    <Box
      sx={{
        mt: compact ? 0 : 1,
        display: compact ? "flex" : "grid",
        flexDirection: compact ? "column" : undefined,
        gridTemplateColumns: compact
          ? undefined
          : {
              xs: "1fr",
              lg: "minmax(280px, 0.9fr) minmax(0, 1.6fr)",
            },
        gap: 2,
      }}
    >
      <SavedFieldsPanel
        fields={fields}
        selectedFieldId={selectedFieldId}
        selectedField={selectedField}
        loadingFields={loadingFields}
        deletingField={deletingField}
        onSelectField={onSelectField}
        onRefresh={onRefreshFields}
        onFocusSelected={onFocusSelected}
        onDeleteSelected={onDeleteSelected}
      />

      <Stack
        direction={compact ? "column" : { xs: "column", lg: "row" }}
        spacing={1}
        alignItems={{ xs: "stretch", lg: "flex-start" }}
      >
        <FieldBorderPanel
          fieldName={fieldName}
          selectedFieldId={selectedFieldId}
          fieldBorder={fieldBorder}
          metrics={metrics}
          selectedFieldDisplayId={selectedField?.id ?? null}
          savingField={savingField}
          onFieldNameChange={onFieldNameChange}
          onSaveOrUpdate={onSaveOrUpdate}
          onClearBorder={onClearBorder}
          onNewField={onNewField}
        />
      </Stack>
    </Box>
  );
}
