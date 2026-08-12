import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Button,
  Card,
  CardContent,
  Step,
  StepLabel,
  Stepper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useMemo, useState } from "react";
import { useCreateAgricultureField, usePatchAgricultureProfile } from "../hooks";
import {
  polygonRing,
  validateAgriculturePolygon,
  type AgriculturePolygon,
} from "../geometry";
import { AgricultureGeometryMapEditor } from "./AgricultureGeometryMapEditor";

const steps = ["Locate / Name", "Draw or import boundary", "Crop / season context", "Review"];

export function AgricultureFieldSetupWizard() {
  const create = useCreateAgricultureField();
  const patchProfile = usePatchAgricultureProfile();
  const [activeStep, setActiveStep] = useState(0);
  const [name, setName] = useState("");
  const [cropType, setCropType] = useState("");
  const [season, setSeason] = useState("");
  const [growthStage, setGrowthStage] = useState("");
  const [boundary, setBoundary] = useState<AgriculturePolygon | null>(null);
  const [geoJsonText, setGeoJsonText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const boundaryRing = useMemo(() => polygonRing(boundary), [boundary]);
  const setValidatedBoundary = (value: unknown) => {
    try {
      const valid = validateAgriculturePolygon(value);
      setBoundary(valid);
      setGeoJsonText(JSON.stringify(valid, null, 2));
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid field boundary.");
    }
  };
  const next = () => {
    if (activeStep === 0 && !name.trim()) {
      setError("Field name is required.");
      return;
    }
    if (activeStep === 1) {
      try {
        validateAgriculturePolygon(boundary);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Draw or import a valid boundary.");
        return;
      }
    }
    setError(null);
    setActiveStep((current) => Math.min(steps.length - 1, current + 1));
  };
  const submit = () => {
    try {
      const validBoundary = validateAgriculturePolygon(boundary);
      if (!name.trim()) throw new Error("Field name is required.");
      setError(null);
      create.mutate({ name: name.trim(), boundary: validBoundary }, {
        onSuccess: (field) => {
          patchProfile.mutate({
            fieldId: field.field_id,
            payload: {
              crop_type: cropType.trim() || null,
              season: season.trim() || null,
              growth_stage: growthStage.trim() || null,
            },
          }, {
            onSuccess: () => {
              setActiveStep(0);
              setName("");
              setCropType("");
              setSeason("");
              setGrowthStage("");
              setBoundary(null);
              setGeoJsonText("");
            },
          });
        },
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid field setup.");
    }
  };

  return (
    <Card component="section" variant="outlined" aria-labelledby="field-setup-title">
      <CardContent>
        <Stack spacing={2}>
          <div>
            <Typography id="field-setup-title" variant="h6">Set up a field</Typography>
            <Typography variant="body2" color="text.secondary">
              Create a reusable field boundary without entering coordinates.
            </Typography>
          </div>
          <Stepper activeStep={activeStep} alternativeLabel>
            {steps.map((label) => <Step key={label}><StepLabel>{label}</StepLabel></Step>)}
          </Stepper>
          {error ? <Alert severity="error" role="alert">{error}</Alert> : null}
          {create.isError || patchProfile.isError ? <Alert severity="error">Unable to save the complete field setup. Check the boundary, crop context, and your permissions.</Alert> : null}

          {activeStep === 0 ? (
            <Stack spacing={1.5}>
              <TextField autoFocus required label="Field name" value={name} onChange={(event) => setName(event.target.value)} helperText="Use the name your team recognizes." />
              <Typography variant="body2" color="text.secondary">The map opens around your boundary when you draw or import it.</Typography>
            </Stack>
          ) : null}
          {activeStep === 1 ? (
            <Stack spacing={1.5}>
              <AgricultureGeometryMapEditor
                boundary={boundaryRing}
                onBoundaryChange={(ring) => setValidatedBoundary({ type: "Polygon", coordinates: [ring] })}
              />
              <Button component="label" variant="outlined" sx={{ minHeight: 44, alignSelf: "flex-start" }}>
                Import GeoJSON
                <input
                  hidden
                  type="file"
                  accept=".geojson,.json,application/geo+json,application/json"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    void file.text().then((text) => {
                      setGeoJsonText(text);
                      try { setValidatedBoundary(JSON.parse(text)); }
                      catch { setError("The selected file is not valid GeoJSON."); }
                    });
                  }}
                />
              </Button>
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>Advanced GeoJSON</AccordionSummary>
                <AccordionDetails>
                  <Stack spacing={1}>
                    <TextField label="Boundary GeoJSON (EPSG:4326)" value={geoJsonText} onChange={(event) => setGeoJsonText(event.target.value)} multiline minRows={5} fullWidth />
                    <Button onClick={() => {
                      try { setValidatedBoundary(JSON.parse(geoJsonText)); }
                      catch { setError("Boundary GeoJSON is not valid JSON."); }
                    }}>Apply GeoJSON</Button>
                  </Stack>
                </AccordionDetails>
              </Accordion>
            </Stack>
          ) : null}
          {activeStep === 2 ? (
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField label="Crop type" value={cropType} onChange={(event) => setCropType(event.target.value)} />
              <TextField label="Season" value={season} onChange={(event) => setSeason(event.target.value)} />
              <TextField label="Growth stage" value={growthStage} onChange={(event) => setGrowthStage(event.target.value)} />
            </Stack>
          ) : null}
          {activeStep === 3 ? (
            <Stack spacing={0.5}>
              <Typography variant="subtitle2">{name}</Typography>
              <Typography variant="body2">Boundary: {boundaryRing?.length ?? 0} points</Typography>
              <Typography variant="body2">Crop: {cropType || "Not specified"} · Season: {season || "Not specified"} · Stage: {growthStage || "Not specified"}</Typography>
              <Alert severity="info">The server performs authoritative geometry and self-intersection validation when the field is saved.</Alert>
            </Stack>
          ) : null}
          <Stack direction="row" justifyContent="space-between">
            <Button sx={{ minHeight: 44 }} disabled={activeStep === 0 || create.isPending || patchProfile.isPending} onClick={() => { setError(null); setActiveStep((current) => current - 1); }}>Back</Button>
            {activeStep < steps.length - 1 ? (
              <Button sx={{ minHeight: 44 }} variant="contained" onClick={next}>Continue</Button>
            ) : (
              <Button sx={{ minHeight: 44 }} variant="contained" disabled={create.isPending || patchProfile.isPending} onClick={submit}>
                {create.isPending || patchProfile.isPending ? "Creating…" : "Create field"}
              </Button>
            )}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}
