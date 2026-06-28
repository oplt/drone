import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  InputAdornment,
  MenuItem,
  Stack,
  TextField,
} from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import type { WarehouseMapOut } from "../types";
import type { WarehouseScannedMapResponse } from "../types/missions";
import { getWarehouseMapId } from "../scannedMapSelectors";
import { COMPACT_FIELD_SX, type CreateMapForm } from "../warehousePageSupport";
import {
  createWarehouseMapSetup,
  lockWarehouseMapSetup,
  previewWarehouseMapSetup,
} from "../api/warehouseMapsApi";
import type { WarehouseMapSetup, WarehouseMapSetupPreview } from "../types";
import { WarehouseLayoutEditor } from "./WarehouseLayoutEditor";
import { WarehouseCoordinateDiagnosticsPanel } from "./WarehouseCoordinateDiagnosticsPanel";
import {
  estimateScanOdomAlignment,
  runFloorPlaneRansac,
} from "../api/warehouseCoordinateSetupApi";

type Props = {
  maps: WarehouseMapOut[];
  scannedMaps: WarehouseScannedMapResponse[];
  selectedId: number | null;
  loading: boolean;
  creating: boolean;
  deleting: boolean;
  onSelect: (id: number | null) => void;
  onRefresh: () => void;
  onCreate: (form: CreateMapForm) => Promise<boolean>;
  onDelete: (map: WarehouseMapOut | undefined, assetCount: number) => void;
  getToken: () => string | null;
};

const emptyForm: CreateMapForm = { name: "", width_m: "", length_m: "" };

export function WarehouseMapSetupPanel({
  maps,
  scannedMaps,
  selectedId,
  loading,
  creating,
  deleting,
  onSelect,
  onRefresh,
  onCreate,
  onDelete,
  getToken,
}: Props) {
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateMapForm>(emptyForm);
  const selectedMap = maps.find((map) => map.id === selectedId);
  const [polygonText, setPolygonText] = useState("");
  const [origin, setOrigin] = useState({ x: "0", y: "0", z: "0", yaw: "0" });
  const [alignment, setAlignment] = useState("0");
  const [reference, setReference] = useState<"north" | "aisle">("aisle");
  const [localizationStdM, setLocalizationStdM] = useState("0.10");
  const [maxTransformAgeS, setMaxTransformAgeS] = useState("300");
  const [mapResolutionM, setMapResolutionM] = useState("0.05");
  const [knownDistance, setKnownDistance] = useState({
    expected: "",
    measured: "",
  });
  const [draft, setDraft] = useState<WarehouseMapSetup | null>(null);
  const [preview, setPreview] = useState<WarehouseMapSetupPreview | null>(null);
  const [setupBusy, setSetupBusy] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [floorPointsText, setFloorPointsText] = useState("");
  const [floorPlane, setFloorPlane] = useState<Record<string, unknown> | null>(null);
  const [axisFlipRad, setAxisFlipRad] = useState("0");
  const [scanOdomAlignment, setScanOdomAlignment] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    setPolygonText(
      (selectedMap?.polygon_local_m ?? [])
        .map((point) => point.join(", "))
        .join("\n"),
    );
    const transform = selectedMap?.origin_transform;
    const rotation = transform?.rotation;
    const yaw = rotation
      ? (Math.atan2(
          2 * (rotation.w * rotation.z + rotation.x * rotation.y),
          1 - 2 * (rotation.y ** 2 + rotation.z ** 2),
        ) *
          180) /
        Math.PI
      : 0;
    setOrigin({
      x: String(transform?.translation.x ?? 0),
      y: String(transform?.translation.y ?? 0),
      z: String(transform?.translation.z ?? 0),
      yaw: String(yaw),
    });
    setAlignment(String(selectedMap?.alignment_deg ?? 0));
    setReference(selectedMap?.alignment_reference ?? "aisle");
    setDraft(null);
    setPreview(null);
  }, [selectedMap]);

  const saveDraft = async () => {
    if (!selectedId) return;
    try {
      setSetupBusy(true);
      setSetupError(null);
      const polygon = polygonText.split(/\n+/).map((line) => {
        const [x, y] = line.split(",").map(Number);
        if (!Number.isFinite(x) || !Number.isFinite(y))
          throw new Error("Each boundary line must be x, y");
        return [x, y] as [number, number];
      });
      const yaw = (Number(origin.yaw) * Math.PI) / 180;
      const variance = Number(localizationStdM) ** 2;
      const covariance = Array<number>(36).fill(0);
      covariance[0] = covariance[7] = covariance[14] = variance;
      const created = await createWarehouseMapSetup(
        selectedId,
        {
          polygon_local_m: polygon,
          origin_transform: {
            translation: {
              x: Number(origin.x),
              y: Number(origin.y),
              z: Number(origin.z),
            },
            rotation: {
              x: 0,
              y: 0,
              z: Math.sin(yaw / 2),
              w: Math.cos(yaw / 2),
            },
          },
          alignment_deg: Number(alignment),
          alignment_reference: reference,
          source: "operator_ui",
          confidence: 1,
          transform_timestamp: new Date().toISOString(),
          max_transform_age_s: Number(maxTransformAgeS),
          covariance,
          localization_method: "operator_survey",
          map_resolution_m: Number(mapResolutionM),
          scale: 1,
          known_distance_expected_m: knownDistance.expected
            ? Number(knownDistance.expected)
            : null,
          known_distance_measured_m: knownDistance.measured
            ? Number(knownDistance.measured)
            : null,
        },
        getToken(),
      );
      setDraft(created);
      setPreview(
        await previewWarehouseMapSetup(selectedId, created.id, getToken()),
      );
    } catch (error) {
      setSetupError(
        error instanceof Error ? error.message : "Could not save setup draft",
      );
    } finally {
      setSetupBusy(false);
    }
  };

  const lockDraft = async () => {
    if (!selectedId || !draft) return;
    try {
      setSetupBusy(true);
      await lockWarehouseMapSetup(selectedId, draft.id, getToken());
      setDraft(null);
      setPreview(null);
      onRefresh();
    } catch (error) {
      setSetupError(
        error instanceof Error ? error.message : "Could not lock setup",
      );
    } finally {
      setSetupBusy(false);
    }
  };

  return (
    <Stack
      direction="row"
      spacing={0.75}
      alignItems="flex-start"
      useFlexGap
      sx={{ flexWrap: "wrap", minWidth: 0 }}
    >
      <TextField
        variant="filled"
        select
        size="small"
        label="Map"
        value={selectedId == null ? "" : String(selectedId)}
        onChange={(event) =>
          onSelect(event.target.value ? Number(event.target.value) : null)
        }
        disabled={loading}
        helperText={
          maps.length === 0
            ? "No maps yet"
            : selectedMap?.area_m2 != null
              ? `${Math.round(selectedMap.area_m2)} m²`
              : selectedId != null
                ? `#${selectedId}`
                : undefined
        }
        sx={{
          ...COMPACT_FIELD_SX,
          flex: "1 1 160px",
          minWidth: 140,
          maxWidth: 360,
        }}
      >
        {maps.length === 0 && (
          <MenuItem value="">No warehouse maps registered</MenuItem>
        )}
        {maps.map((map) => (
          <MenuItem key={map.id} value={String(map.id)}>
            {map.name}
            {map.area_m2 != null ? ` • ${Math.round(map.area_m2)} m²` : ""}
          </MenuItem>
        ))}
      </TextField>
      <Stack direction="row" spacing={0.25} sx={{ pt: 0.25 }}>
        <ActionIconButton
          variant="refresh"
          title="Refresh"
          loading={loading}
          onClick={onRefresh}
        />
        <ActionIconButton
          variant="add"
          title={showCreate ? "Cancel" : "New Map"}
          color={showCreate ? "primary" : "default"}
          onClick={() => setShowCreate((value) => !value)}
        />
        <ActionIconButton
          variant="delete"
          title={deleting ? "Deleting…" : "Delete Map"}
          color="error"
          loading={deleting}
          disabled={selectedId == null}
          onClick={() =>
            onDelete(
              selectedMap,
              scannedMaps.filter(
                (scan) => getWarehouseMapId(scan) === selectedId,
              ).length,
            )
          }
        />
      </Stack>
      {showCreate && (
        <>
          <TextField
            variant="filled"
            size="small"
            label="Name"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            placeholder="e.g. Aisle A–F"
            sx={{ ...COMPACT_FIELD_SX, flex: "1 1 120px", minWidth: 100 }}
          />
          {(["width_m", "length_m"] as const).map((key) => (
            <TextField
              key={key}
              variant="filled"
              size="small"
              type="number"
              label={key === "width_m" ? "Width" : "Length"}
              inputProps={{ min: 0.1, step: 0.5 }}
              InputProps={{
                endAdornment: <InputAdornment position="end">m</InputAdornment>,
              }}
              value={form[key]}
              onChange={(event) =>
                setForm({ ...form, [key]: event.target.value })
              }
              sx={{ ...COMPACT_FIELD_SX, flex: "0 1 88px", minWidth: 72 }}
            />
          ))}
          <ActionIconButton
            variant="add"
            title={creating ? "Creating…" : "Create Map"}
            color="primary"
            loading={creating}
            onClick={() => {
              void onCreate(form).then((created) => {
                if (!created) return;
                setForm(emptyForm);
                setShowCreate(false);
              });
            }}
            sx={{ mt: 0.25 }}
          />
        </>
      )}
      {selectedMap && (
        <Stack spacing={1} sx={{ flex: "1 0 100%", pt: 1 }}>
          <TextField
            multiline
            minRows={4}
            label="Boundary polygon (x, y per line)"
            value={polygonText}
            onChange={(event) => setPolygonText(event.target.value)}
          />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            {(["x", "y", "z", "yaw"] as const).map((key) => (
              <TextField
                key={key}
                size="small"
                type="number"
                label={`Origin ${key}${key === "yaw" ? " (deg)" : " (m)"}`}
                value={origin[key]}
                onChange={(event) =>
                  setOrigin({ ...origin, [key]: event.target.value })
                }
              />
            ))}
            <TextField
              size="small"
              type="number"
              label="Alignment (deg)"
              value={alignment}
              onChange={(event) => setAlignment(event.target.value)}
            />
            <TextField
              select
              size="small"
              label="Alignment reference"
              value={reference}
              onChange={(event) =>
                setReference(event.target.value as "north" | "aisle")
              }
            >
              <MenuItem value="aisle">Aisle</MenuItem>
              <MenuItem value="north">North</MenuItem>
            </TextField>
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <TextField
              size="small"
              type="number"
              label="Localization std (m)"
              value={localizationStdM}
              onChange={(event) => setLocalizationStdM(event.target.value)}
            />
            <TextField
              size="small"
              type="number"
              label="Transform max age (s)"
              value={maxTransformAgeS}
              onChange={(event) => setMaxTransformAgeS(event.target.value)}
            />
            <TextField
              size="small"
              type="number"
              label="Map resolution (m)"
              value={mapResolutionM}
              onChange={(event) => setMapResolutionM(event.target.value)}
            />
            <TextField
              size="small"
              type="number"
              label="Known distance (m)"
              value={knownDistance.expected}
              onChange={(event) =>
                setKnownDistance({
                  ...knownDistance,
                  expected: event.target.value,
                })
              }
            />
            <TextField
              size="small"
              type="number"
              label="Measured distance (m)"
              value={knownDistance.measured}
              onChange={(event) =>
                setKnownDistance({
                  ...knownDistance,
                  measured: event.target.value,
                })
              }
            />
          </Stack>
          <TextField
            multiline
            minRows={3}
            size="small"
            label="Floor sample points (x,y,z per line)"
            value={floorPointsText}
            onChange={(event) => setFloorPointsText(event.target.value)}
          />
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              variant="outlined"
              disabled={setupBusy || !selectedMap}
              onClick={() => {
                if (!selectedMap) return;
                const points = floorPointsText
                  .split("\n")
                  .map((line) => line.split(",").map((part) => Number(part.trim())))
                  .filter((row) => row.length >= 3 && row.every((value) => Number.isFinite(value)));
                void runFloorPlaneRansac(selectedMap.id, points, getToken())
                  .then((result) => setFloorPlane(result))
                  .catch((error: unknown) =>
                    setSetupError(
                      error instanceof Error ? error.message : "Floor-plane RANSAC failed",
                    ),
                  );
              }}
            >
              Run floor-plane RANSAC
            </Button>
            <TextField
              size="small"
              type="number"
              label="Axis flip (rad)"
              value={axisFlipRad}
              onChange={(event) => setAxisFlipRad(event.target.value)}
              sx={{ width: 140 }}
            />
            <Button
              size="small"
              variant="outlined"
              disabled={setupBusy || !selectedMap || !floorPlane}
              onClick={() => {
                if (!selectedMap || !floorPlane) return;
                void estimateScanOdomAlignment(
                  selectedMap.id,
                  {
                    floor_plane: floorPlane,
                    yaw_flip_rad: Number(axisFlipRad) || 0,
                  },
                  getToken(),
                )
                  .then((alignment) => setScanOdomAlignment(alignment))
                  .catch((error: unknown) =>
                    setSetupError(
                      error instanceof Error ? error.message : "Scan odom alignment failed",
                    ),
                  );
              }}
            >
              Estimate scan_odom alignment
            </Button>
          </Stack>
          {floorPlane ? (
            <Alert severity={floorPlane.ok ? "success" : "warning"}>
              RANSAC inliers {String(floorPlane.inlier_count ?? 0)} /{" "}
              {String(floorPlane.point_count ?? 0)} · residual RMS{" "}
              {String(floorPlane.residual_rms_m ?? "n/a")} m · dominant yaw{" "}
              {String(floorPlane.dominant_yaw_rad ?? "n/a")} rad
            </Alert>
          ) : null}
          {scanOdomAlignment ? (
            <Alert severity="info">
              Scan_odom alignment residual RMS{" "}
              {String(scanOdomAlignment.residual_rms_m ?? "n/a")} m · yaw offset{" "}
              {String(scanOdomAlignment.yaw_offset_rad ?? "n/a")} rad
            </Alert>
          ) : null}
          {setupError && <Alert severity="error">{setupError}</Alert>}
          {preview && (
            <Alert severity="warning">
              Locking creates a new coordinate revision. Existing pinned
              children: {preview.affected.models} models,{" "}
              {preview.affected.layouts} layouts, {preview.affected.targets}{" "}
              targets, {preview.affected.missions} missions. {preview.policy}
            </Alert>
          )}
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              disabled={setupBusy}
              onClick={() => void saveDraft()}
            >
              Preview changes
            </Button>
            <Button
              variant="contained"
              disabled={setupBusy || !draft || !preview}
              onClick={() => void lockDraft()}
            >
              Lock origin & boundary
            </Button>
          </Stack>
          <WarehouseCoordinateDiagnosticsPanel
            warehouseMapId={selectedMap.id}
            token={getToken()}
          />
          <WarehouseLayoutEditor
            warehouseMapId={selectedMap.id}
            token={getToken()}
          />
        </Stack>
      )}
    </Stack>
  );
}
