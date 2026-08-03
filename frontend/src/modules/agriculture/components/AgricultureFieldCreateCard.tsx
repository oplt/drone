import { Alert, Button, Card, CardContent, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useCreateAgricultureField } from "../hooks";

const starter = { type: "Polygon", coordinates: [[[4.35, 50.85], [4.36, 50.85], [4.36, 50.86], [4.35, 50.86], [4.35, 50.85]]] };

export function AgricultureFieldCreateCard() {
  const create = useCreateAgricultureField();
  const [name, setName] = useState("");
  const [text, setText] = useState(JSON.stringify(starter, null, 2));
  const [error, setError] = useState<string | null>(null);
  const submit = () => {
    try {
      const boundary = JSON.parse(text) as Record<string, unknown>;
      if (boundary.type !== "Polygon" && !(boundary.geometry as Record<string, unknown> | undefined)?.type) throw new Error("Boundary must be a GeoJSON Polygon.");
      if (!name.trim()) throw new Error("Field name is required.");
      setError(null); create.mutate({ name: name.trim(), boundary });
    } catch (exc) { setError(exc instanceof Error ? exc.message : "Invalid field boundary."); }
  };
  return <Card variant="outlined" component="section" aria-labelledby="create-agri-field-title"><CardContent><Stack spacing={1.5}><Typography id="create-agri-field-title" variant="h6">Create agriculture field</Typography><Typography variant="body2" color="text.secondary">Import a Polygon in WGS84 longitude/latitude. The server validates area, holes and CRS before saving.</Typography>{error ? <Alert severity="error">{error}</Alert> : null}{create.isError ? <Alert severity="error">Unable to create field. Check the boundary and your permissions.</Alert> : null}<TextField label="Field name" value={name} onChange={(event) => setName(event.target.value)} required fullWidth /><TextField label="Boundary GeoJSON" value={text} onChange={(event) => setText(event.target.value)} multiline minRows={4} fullWidth inputProps={{ "aria-label": "New agriculture field boundary GeoJSON" }} /><Button variant="contained" onClick={submit} disabled={create.isPending}>Create field</Button></Stack></CardContent></Card>;
}
