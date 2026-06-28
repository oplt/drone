import type {
  LayoutDocument,
  LayoutEntity,
  LayoutKind,
} from "../api/warehouseLayoutApi";

export type WarehouseSceneNode = {
  id: string;
  entityId: number;
  kind: LayoutKind | "dock" | "inspection-target";
  label: string;
  frameId: "warehouse_map";
  parentId?: number;
  x: number;
  y: number;
  z: number;
  width: number;
  depth: number;
  height: number;
};

const finite = (value: unknown, fallback: number) =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;

export function entityToSceneNode(
  kind: LayoutKind,
  entity: LayoutEntity,
): WarehouseSceneNode {
  const geometry = entity.geometry ?? {};
  return {
    id: `${kind}:${entity.id}`,
    entityId: entity.id,
    kind,
    label:
      entity.code ??
      (entity.level != null ? `Level ${entity.level}` : `${kind} ${entity.id}`),
    frameId: "warehouse_map",
    parentId: entity.parent_id,
    x: finite(geometry.x_m, finite(geometry.x, 0)),
    y: finite(geometry.y_m, finite(geometry.y, 0)),
    z: finite(geometry.z_m, finite(geometry.z, 0)),
    width: Math.max(0.2, finite(geometry.width_m, finite(geometry.width, 1))),
    depth: Math.max(0.2, finite(geometry.depth_m, finite(geometry.depth, 1))),
    height: Math.max(
      0.2,
      finite(geometry.height_m, finite(geometry.height, 1)),
    ),
  };
}

export function layoutToScene(document: LayoutDocument): WarehouseSceneNode[] {
  return (Object.entries(document) as [LayoutKind, LayoutEntity[]][]).flatMap(
    ([kind, rows]) => rows.map((row) => entityToSceneNode(kind, row)),
  );
}

export const snapValue = (value: number, grid: number) =>
  grid > 0 ? Math.round(value / grid) * grid : value;

export function moveEntity(
  entity: LayoutEntity,
  x: number,
  y: number,
  grid: number,
): LayoutEntity {
  return {
    ...entity,
    geometry: {
      ...entity.geometry,
      x_m: snapValue(x, grid),
      y_m: snapValue(y, grid),
    },
  };
}
