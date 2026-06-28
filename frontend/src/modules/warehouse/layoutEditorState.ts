import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createLayoutVersion,
  listLayoutVersions,
  loadLayoutDocument,
  saveLayoutDocument,
  validateLayout,
  type LayoutDocument,
  type LayoutEntity,
  type LayoutIssue,
  type LayoutKind,
  type LayoutVersion,
} from "./api/warehouseLayoutApi";
import { useLayoutEditorHistory } from "./hooks/useLayoutEditorHistory";
import { layoutToScene, moveEntity } from "./utils/warehouseLayoutScene";

export const EMPTY_LAYOUT: LayoutDocument = {
  aisles: [],
  racks: [],
  shelves: [],
  bins: [],
  zones: [],
};
export const LAYOUT_LABELS: Record<LayoutKind, string> = {
  aisles: "Aisle",
  racks: "Rack",
  shelves: "Shelf",
  bins: "Bin",
  zones: "Safety zone",
};
const PARENT: Partial<Record<LayoutKind, LayoutKind>> = {
  racks: "aisles",
  shelves: "racks",
  bins: "shelves",
};

export function useWarehouseLayoutEditor(
  warehouseMapId: number,
  token?: string | null,
) {
  const history = useLayoutEditorHistory<LayoutDocument>(EMPTY_LAYOUT);
  const replaceHistory = history.replace;
  const [layout, setLayout] = useState<LayoutVersion | null>(null);
  const [selected, setSelected] = useState<{
    kind: LayoutKind;
    id: number;
  } | null>(null);
  const [mode, setMode] = useState<"2d" | "3d">("2d");
  const [grid, setGrid] = useState(0.25);
  const [issues, setIssues] = useState<LayoutIssue[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nodes = useMemo(
    () => layoutToScene(history.present),
    [history.present],
  );
  const selectedEntity = selected
    ? (history.present[selected.kind].find((row) => row.id === selected.id) ??
      null)
    : null;

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const versions = await listLayoutVersions(warehouseMapId, token);
      const editable =
        versions.filter((item) => item.status === "draft").at(-1) ?? null;
      setLayout(editable);
      replaceHistory(
        editable
          ? await loadLayoutDocument(warehouseMapId, editable.version, token)
          : EMPTY_LAYOUT,
        false,
      );
      setSelected(null);
      setIssues([]);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Layout could not be loaded.",
      );
    } finally {
      setBusy(false);
    }
  }, [replaceHistory, token, warehouseMapId]);

  useEffect(() => void load(), [load]);

  const mutate = (
    kind: LayoutKind,
    id: number,
    update: (row: LayoutEntity) => LayoutEntity,
  ) => {
    history.replace({
      ...history.present,
      [kind]: history.present[kind].map((row) =>
        row.id === id ? update(row) : row,
      ),
    });
  };

  const add = (kind: LayoutKind) => {
    const parentKind = PARENT[kind];
    if (parentKind && selected?.kind !== parentKind) {
      setError(`Select a ${LAYOUT_LABELS[parentKind].toLowerCase()} first.`);
      return;
    }
    const id = -Date.now();
    const count = history.present[kind].length + 1;
    const row: LayoutEntity = {
      id,
      parent_id: parentKind ? selected?.id : undefined,
      code:
        kind === "shelves"
          ? undefined
          : `${LAYOUT_LABELS[kind].slice(0, 1)}${count}`,
      level: kind === "shelves" ? count : undefined,
      kind: kind === "zones" ? "keep_out" : undefined,
      geometry: {
        x_m: count,
        y_m: count,
        z_m: 0,
        width_m: 1,
        depth_m: 1,
        height_m: 1,
      },
      active: true,
    };
    history.replace({
      ...history.present,
      [kind]: [...history.present[kind], row],
    });
    setSelected({ kind, id });
    setError(null);
  };

  const duplicate = () => {
    if (!selected || !selectedEntity) return;
    const id = -Date.now();
    const copy = moveEntity(
      {
        ...selectedEntity,
        id,
        code: selectedEntity.code ? `${selectedEntity.code} copy` : undefined,
      },
      Number(selectedEntity.geometry.x_m ?? 0) + grid,
      Number(selectedEntity.geometry.y_m ?? 0) + grid,
      grid,
    );
    history.replace({
      ...history.present,
      [selected.kind]: [...history.present[selected.kind], copy],
    });
    setSelected({ kind: selected.kind, id });
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      let current = layout;
      if (!current) current = await createLayoutVersion(warehouseMapId, token);
      const revision = await saveLayoutDocument(
        warehouseMapId,
        current,
        history.present,
        token,
      );
      setLayout({ ...current, revision });
      await load();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Layout could not be saved.",
      );
    } finally {
      setBusy(false);
    }
  };

  const runValidation = async () => {
    if (!layout) {
      setIssues([
        {
          code: "layout_unsaved",
          message: "Save draft first.",
          path: "layout",
          severity: "warning",
        },
      ]);
      return;
    }
    const report = await validateLayout(warehouseMapId, layout.version, token);
    setIssues(report.issues);
  };

  const nudgeSelected = (dx: number, dy: number) => {
    if (!selected || !selectedEntity) return;
    mutate(selected.kind, selected.id, (row) =>
      moveEntity(
        row,
        Number(selectedEntity.geometry.x_m ?? 0) + dx,
        Number(selectedEntity.geometry.y_m ?? 0) + dy,
        grid,
      ),
    );
  };

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!selected || !selectedEntity) return;
      const step = event.shiftKey ? grid * 4 : grid;
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        nudgeSelected(-step, 0);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        nudgeSelected(step, 0);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        nudgeSelected(0, step);
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        nudgeSelected(0, -step);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  return {
    ...history,
    layout,
    selected,
    selectedEntity,
    nodes,
    mode,
    grid,
    issues,
    busy,
    error,
    setSelected,
    setMode,
    setGrid,
    setError,
    mutate,
    add,
    duplicate,
    save,
    runValidation,
  };
}
