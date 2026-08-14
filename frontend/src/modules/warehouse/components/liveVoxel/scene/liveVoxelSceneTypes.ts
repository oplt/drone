import type { LiveMapColorMode, LiveMapLayerKey } from "../../utils/liveMapLayerUtils";

export type LiveVoxelLayers = Record<LiveMapLayerKey, boolean>;

export type LiveVoxelRenderOptions = {
  pointSize: number;
  colorMode: LiveMapColorMode;
  layerPointBudget: Record<LiveMapLayerKey, number>;
};
