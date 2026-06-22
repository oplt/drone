import {
  PHOTOGRAMMETRY_GRID_COPY,
  GridMissionParamsSection,
} from "../../mission-planning/components/GridMissionParamsSection";
import type { GridParams } from "../../mission-planning";
import type { LonLat } from "../../fields";

export function PhotogrammetryGridParamsSection({
  gridParams,
  setGridParams,
  fieldBorder,
  gridPreview,
  gridPreviewStats,
  previewLegStats,
  gridPreviewTooDense,
  gridPreviewError,
  previewLoading,
}: {
  gridParams: GridParams;
  setGridParams: React.Dispatch<React.SetStateAction<GridParams>>;
  fieldBorder: LonLat[] | null;
  gridPreview: { lat: number; lon: number }[] | null | undefined;
  gridPreviewStats: { route_m?: number; rows?: number } | null | undefined;
  previewLegStats: { workLegs: number; transitLegs: number } | null;
  gridPreviewTooDense: boolean;
  gridPreviewError: string | null | undefined;
  previewLoading: boolean;
}) {
  return (
    <GridMissionParamsSection
      copy={PHOTOGRAMMETRY_GRID_COPY}
      gridParams={gridParams}
      setGridParams={setGridParams}
      fieldBorder={fieldBorder}
      gridPreview={gridPreview}
      gridPreviewStats={gridPreviewStats}
      previewLegStats={previewLegStats}
      gridPreviewTooDense={gridPreviewTooDense}
      gridPreviewError={gridPreviewError}
      previewLoading={previewLoading}
    />
  );
}
