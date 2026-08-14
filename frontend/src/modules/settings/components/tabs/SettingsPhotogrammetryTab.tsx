import { FormControlLabel, Stack, Switch, TextField, Typography } from "@mui/material";
import Grid from "@mui/material/Grid";
import { DEFAULT_SETTINGS_DOC } from "../../settingsDefaults";
import { SecretField } from "../SecretField";
import type { SettingsTabPanelProps } from "../settingsTabProps";

export function SettingsPhotogrammetryTab({ doc, update }: SettingsTabPanelProps) {
  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, md: 6 }}>
        <Typography variant="h6" gutterBottom>
          Storage & Sync
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="Drone Sync Dir"
            placeholder={DEFAULT_SETTINGS_DOC.photogrammetry.PHOTOGRAMMETRY_DRONE_SYNC_DIR}
            value={doc.photogrammetry?.PHOTOGRAMMETRY_DRONE_SYNC_DIR}
            onChange={(e) =>
              update("photogrammetry", "PHOTOGRAMMETRY_DRONE_SYNC_DIR", e.target.value)
            }
          />
          <TextField
            variant="filled"
            fullWidth
            label="Capture Staging Dir"
            placeholder={
              DEFAULT_SETTINGS_DOC.photogrammetry.PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR
            }
            value={doc.photogrammetry?.PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR}
            onChange={(e) =>
              update(
                "photogrammetry",
                "PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR",
                e.target.value,
              )
            }
          />
          <TextField
            variant="filled"
            fullWidth
            label="Inputs Dir"
            placeholder={DEFAULT_SETTINGS_DOC.photogrammetry.PHOTOGRAMMETRY_INPUTS_DIR}
            value={doc.photogrammetry?.PHOTOGRAMMETRY_INPUTS_DIR}
            onChange={(e) =>
              update("photogrammetry", "PHOTOGRAMMETRY_INPUTS_DIR", e.target.value)
            }
          />
          <TextField
            variant="filled"
            fullWidth
            label="Storage Dir"
            placeholder={DEFAULT_SETTINGS_DOC.photogrammetry.PHOTOGRAMMETRY_STORAGE_DIR}
            value={doc.photogrammetry?.PHOTOGRAMMETRY_STORAGE_DIR}
            onChange={(e) =>
              update("photogrammetry", "PHOTOGRAMMETRY_STORAGE_DIR", e.target.value)
            }
          />
          <TextField
            variant="filled"
            fullWidth
            label="Storage Base URL"
            placeholder={DEFAULT_SETTINGS_DOC.photogrammetry.PHOTOGRAMMETRY_STORAGE_BASE_URL}
            value={doc.photogrammetry?.PHOTOGRAMMETRY_STORAGE_BASE_URL}
            onChange={(e) =>
              update("photogrammetry", "PHOTOGRAMMETRY_STORAGE_BASE_URL", e.target.value)
            }
          />
          <TextField
            variant="filled"
            fullWidth
            label="3D Tiles Command"
            placeholder="(none)"
            value={doc.photogrammetry?.PHOTOGRAMMETRY_3DTILES_CMD}
            onChange={(e) =>
              update("photogrammetry", "PHOTOGRAMMETRY_3DTILES_CMD", e.target.value)
            }
          />
          <FormControlLabel
            control={
              <Switch
                checked={doc.photogrammetry?.PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET}
                onChange={(e) =>
                  update(
                    "photogrammetry",
                    "PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET",
                    e.target.checked,
                  )
                }
              />
            }
            label="Allow Minimal Tileset (Dev)"
          />
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, md: 6 }}>
        <Typography variant="h6" gutterBottom>
          WebODM & Queue
        </Typography>
        <Stack spacing={3}>
          <TextField
            variant="filled"
            fullWidth
            label="WebODM Base URL"
            placeholder={DEFAULT_SETTINGS_DOC.photogrammetry.WEBODM_BASE_URL}
            value={doc.photogrammetry?.WEBODM_BASE_URL}
            onChange={(e) => update("photogrammetry", "WEBODM_BASE_URL", e.target.value)}
          />
          <SecretField
            fullWidth
            label="WebODM API Token"
            placeholder="(none)"
            value={doc.photogrammetry?.WEBODM_API_TOKEN}
            onChange={(e) => update("photogrammetry", "WEBODM_API_TOKEN", e.target.value)}
          />
          <TextField
            variant="filled"
            fullWidth
            type="number"
            label="WebODM Project ID"
            placeholder={String(DEFAULT_SETTINGS_DOC.photogrammetry.WEBODM_PROJECT_ID)}
            value={doc.photogrammetry?.WEBODM_PROJECT_ID}
            onChange={(e) =>
              update("photogrammetry", "WEBODM_PROJECT_ID", Number(e.target.value))
            }
          />
          <FormControlLabel
            control={
              <Switch
                checked={doc.photogrammetry?.WEBODM_MOCK_MODE}
                onChange={(e) =>
                  update("photogrammetry", "WEBODM_MOCK_MODE", e.target.checked)
                }
              />
            }
            label="WebODM Mock Mode"
          />
          <TextField
            variant="filled"
            fullWidth
            label="Mapping Job Queue Backend"
            placeholder={DEFAULT_SETTINGS_DOC.photogrammetry.MAPPING_JOB_QUEUE_BACKEND}
            value={doc.photogrammetry?.MAPPING_JOB_QUEUE_BACKEND}
            onChange={(e) =>
              update("photogrammetry", "MAPPING_JOB_QUEUE_BACKEND", e.target.value)
            }
          />
          <TextField
            variant="filled"
            fullWidth
            label="Celery Photogrammetry Queue"
            placeholder={DEFAULT_SETTINGS_DOC.photogrammetry.CELERY_PHOTOGRAMMETRY_QUEUE}
            value={doc.photogrammetry?.CELERY_PHOTOGRAMMETRY_QUEUE}
            onChange={(e) =>
              update("photogrammetry", "CELERY_PHOTOGRAMMETRY_QUEUE", e.target.value)
            }
          />
          <SecretField
            fullWidth
            label="Asset Signing Secret"
            placeholder="(uses jwt_secret)"
            value={doc.photogrammetry?.PHOTOGRAMMETRY_ASSET_SIGNING_SECRET}
            onChange={(e) =>
              update("photogrammetry", "PHOTOGRAMMETRY_ASSET_SIGNING_SECRET", e.target.value)
            }
          />
        </Stack>
      </Grid>
    </Grid>
  );
}
