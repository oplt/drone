import type {
  TerraDrawFeature,
  TerraDrawEditorMode,
  TerraDrawToolMode,
} from "../maps";
import type { CesiumViewMode, DrawMode } from "../maps";

export type Waypoint = { lat: number; lon: number; alt: number };

export type { CesiumViewMode, DrawMode };
export type TerraFeature = TerraDrawFeature;
export type { TerraDrawEditorMode, TerraDrawToolMode };

export interface MissionStatus {
  flight_id?: string;
  mission_name?: string;
  telemetry?: {
    running: boolean;
    active_connections?: number;
    has_position_data?: boolean;
    position?: {
      lat?: number;
      lon?: number;
      lng?: number;
      alt?: number;
      relative_alt?: number;
    };
  };
  orchestrator?: {
    drone_connected: boolean;
  };
}
