import {
  Box,
  Card,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { ModelEvaluation } from "../visionTypes";
import { percent } from "../evaluationDisplay";
import { resolveVisionMediaUrl } from "../visionApi";

export function EvaluationDetails({ data }: { data: ModelEvaluation }) {
  const previews = data.artifacts.filter((artifact) => artifact.name.startsWith("val_batch"));
  return (
    <>
      <TableContainer component={Card} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              {['Class', 'Precision', 'Recall', 'F1', 'mAP50', 'mAP75', 'mAP50–95'].map((label) => (
                <TableCell key={label} align={label === 'Class' ? 'left' : 'right'}>{label}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {data.per_class.map((metric) => (
              <TableRow key={metric.class_index}>
                <TableCell>{metric.class_name.replaceAll("_", " ")}</TableCell>
                <TableCell align="right">{percent(metric.precision)}</TableCell>
                <TableCell align="right">{percent(metric.recall)}</TableCell>
                <TableCell align="right">{percent(metric.f1)}</TableCell>
                <TableCell align="right">{percent(metric.map50)}</TableCell>
                <TableCell align="right">{percent(metric.map75)}</TableCell>
                <TableCell align="right">{percent(metric.map50_95)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      {previews.length ? (
        <Box>
          <Typography variant="h6" gutterBottom>Validation previews</Typography>
          <Grid container spacing={2}>
            {previews.map((artifact) => (
              <Grid key={artifact.name} size={{ xs: 12, md: 4 }}>
                <Card variant="outlined">
                  <Box component="img" src={resolveVisionMediaUrl(artifact.url)} alt="Validation prediction preview" loading="lazy" sx={{ display: "block", width: "100%" }} />
                </Card>
              </Grid>
            ))}
          </Grid>
        </Box>
      ) : null}
    </>
  );
}
