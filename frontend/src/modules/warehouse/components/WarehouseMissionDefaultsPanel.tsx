import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
} from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import {
  MISSION_DEFAULT_VALUE_SX,
  toMissionDefaultColumns,
  type WarehouseMissionDefaultsDraft,
  type WarehouseMissionDefaultsKey,
} from "../warehouseMissionDefaults";

type Props = {
  draft: WarehouseMissionDefaultsDraft | null;
  saving: boolean;
  successMessage: string | null;
  onChange: (key: WarehouseMissionDefaultsKey, value: string) => void;
  onSave: () => void;
};

const headerCellSx = { py: 0.5, fontSize: "0.7rem" } as const;

export function WarehouseMissionDefaultsPanel({
  draft,
  saving,
  successMessage,
  onChange,
  onSave,
}: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const columns = useMemo(
    () => toMissionDefaultColumns(showAdvanced),
    [showAdvanced],
  );

  if (!draft) {
    return (
      <Alert severity="info">
        Warehouse mission defaults are unavailable right now.
      </Alert>
    );
  }

  return (
    <>
      <Stack direction="row" justifyContent="flex-end" sx={{ mb: 1 }}>
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={showAdvanced}
              onChange={(event) => setShowAdvanced(event.target.checked)}
            />
          }
          label="Advanced"
        />
      </Stack>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
          gap: 1,
        }}
      >
        {columns.map((rows, columnIndex) => (
          <Box key={columnIndex} sx={{ minWidth: 0, overflowX: "hidden" }}>
            <Table size="small" sx={{ width: "100%", tableLayout: "fixed" }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ ...headerCellSx, width: "58%", pr: 0.75 }}>
                    Parameter
                  </TableCell>
                  <TableCell sx={{ ...headerCellSx, width: "42%", pl: 0.5 }}>
                    Value
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.key}>
                    <TableCell
                      sx={{
                        width: "58%",
                        py: 0.5,
                        pr: 0.75,
                        fontSize: "0.7rem",
                        whiteSpace: "normal",
                        wordBreak: "break-word",
                        lineHeight: 1.2,
                      }}
                    >
                      {row.label}
                    </TableCell>
                    <TableCell sx={{ width: "42%", py: 0.5, pl: 0.5 }}>
                      {row.kind === "select" ? (
                        <TextField
                          variant="filled"
                          select
                          size="small"
                          value={draft[row.key]}
                          onChange={(event) =>
                            onChange(row.key, event.target.value)
                          }
                          sx={MISSION_DEFAULT_VALUE_SX}
                        >
                          {row.options.map((option) => (
                            <MenuItem
                              key={option.value}
                              value={option.value}
                              sx={{ fontSize: "0.68rem", py: 0.25 }}
                            >
                              {option.label}
                            </MenuItem>
                          ))}
                        </TextField>
                      ) : (
                        <TextField
                          variant="filled"
                          size="small"
                          type="number"
                          value={draft[row.key]}
                          placeholder={row.placeholder}
                          onChange={(event) =>
                            onChange(row.key, event.target.value)
                          }
                          inputProps={{ min: row.min, step: row.step }}
                          sx={MISSION_DEFAULT_VALUE_SX}
                        />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        ))}
      </Box>
      <Stack direction="row" justifyContent="flex-end" sx={{ mt: 1.5 }}>
        <ActionIconButton
          variant="upgrade"
          title={saving ? "Updating Parameters…" : "Update Parameters"}
          color="primary"
          loading={saving}
          onClick={onSave}
        />
      </Stack>
      {successMessage && (
        <Alert severity="success" sx={{ mt: 1.5 }}>
          {successMessage}
        </Alert>
      )}
    </>
  );
}
