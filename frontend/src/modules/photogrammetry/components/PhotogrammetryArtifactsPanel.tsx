import { Paper, Stack, Typography } from "@mui/material";

export function PhotogrammetryArtifactsPanel() {
  return (
    <Paper
      variant="outlined"
      sx={{ p: 2, mb: 2, borderRadius: 2, bgcolor: "background.paper" }}
    >
      <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
        Digital Twin Artifacts
      </Typography>
      <Typography variant="body2" sx={{ mb: 1, color: "text.secondary" }}>
        Mission target: build a georeferenced field digital twin via OpenDroneMap/WebODM
        and publish the outputs as the React tasking map. 3D delivery can be streamed as
        3D Tiles directly or via Cesium ion.
      </Typography>
      <Stack spacing={0.5}>
        <Typography variant="caption">
          Orthomosaic (georeferenced 2D texture) delivered as COG GeoTIFF.
        </Typography>
        <Typography variant="caption">
          DSM and optional DTM delivered as COG GeoTIFF.
        </Typography>
        <Typography variant="caption">
          Textured 3D mesh (OBJ/GLTF/etc) converted to 3D Tiles for web streaming.
        </Typography>
        <Typography variant="caption">
          Optional: point cloud (LAS/LAZ) for inspection-grade detail.
        </Typography>
        <Typography variant="caption">
          Processing service: WebODM behind FastAPI as a mapping job service.
        </Typography>
        <Typography variant="caption">
          Deployment: dedicated worker machine recommended; GPU helps but is not mandatory.
        </Typography>
      </Stack>
    </Paper>
  );
}
