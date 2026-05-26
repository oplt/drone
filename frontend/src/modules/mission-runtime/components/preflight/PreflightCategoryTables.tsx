import {
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { PREFLIGHT_CATEGORIES } from "../../preflight/buildPreflightRows";
import { CATEGORY_LABELS } from "../../preflight/preflightUtils";
import type { PreflightRowsByCategory } from "../../preflight/preflightTypes";
import { PreflightStatusDot } from "./PreflightStatusDot";

export function PreflightCategoryTables({
  rowsByCategory,
}: {
  rowsByCategory: PreflightRowsByCategory;
}) {
  return (
    <>
      {PREFLIGHT_CATEGORIES.map((categoryKey) => (
        <Box key={categoryKey}>
          <Typography
            variant="caption"
            sx={{
              fontWeight: 700,
              letterSpacing: 0.2,
              fontFamily: "monospace",
              display: "block",
              mb: 0.2,
            }}
          >
            {CATEGORY_LABELS[categoryKey]}
          </Typography>
          <TableContainer
            sx={{
              border: "1px dashed",
              borderColor: "rgba(35, 70, 58, 0.22)",
              borderRadius: 1.25,
              backgroundColor: "background.paper",
            }}
          >
            <Table
              size="small"
              sx={{
                "& .MuiTableCell-root": {
                  borderColor: "rgba(35, 70, 58, 0.12)",
                  fontFamily: "monospace",
                  fontSize: "0.72rem",
                  py: 0.1,
                  px: 0.5,
                },
              }}
            >
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: "40%" }}>Parameter</TableCell>
                  <TableCell sx={{ width: "22%" }}>Default</TableCell>
                  <TableCell sx={{ width: "26%" }}>Actual</TableCell>
                  <TableCell align="center" sx={{ width: "12%" }}>
                    Status
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rowsByCategory[categoryKey].map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>{row.label}</TableCell>
                    <TableCell>{row.defaultValue}</TableCell>
                    <TableCell>{row.actualValue}</TableCell>
                    <TableCell align="center">
                      <PreflightStatusDot
                        status={row.status}
                        title={`${row.status}: ${row.statusDetail}`}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      ))}
    </>
  );
}
