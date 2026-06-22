import { stripClosedRing, type LonLat } from "../../fields";

export function createFlatBoundaryDrawBridge({
  setFieldBorder,
  setSelectedFieldId,
  onBoundaryDrawStarted,
}: {
  setFieldBorder: (border: LonLat[] | null) => void;
  setSelectedFieldId: (id: number | null) => void;
  onBoundaryDrawStarted?: () => void;
}) {
  return {
    onBoundaryDrawStarted,
    onBoundaryDrawProgress: (coords: LonLat[]) => {
      if (coords.length === 0) return;
      setFieldBorder(stripClosedRing(coords));
      setSelectedFieldId(null);
    },
  };
}

export function createFarmBorderDrawBridge({
  setFarmBorder,
  onBoundaryDrawStarted,
}: {
  setFarmBorder: (border: LonLat[] | null) => void;
  onBoundaryDrawStarted?: () => void;
}) {
  return {
    onBoundaryDrawStarted,
    onBoundaryDrawProgress: (coords: LonLat[]) => {
      if (coords.length === 0) return;
      setFarmBorder(stripClosedRing(coords));
    },
  };
}
