import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";
import type { WarehouseLiveVoxelMapState } from "../hooks/useWarehouseLiveVoxelMap";
import { poseToVec3, toRenderChunks } from "../utils/liveMapRenderModel";

export type LiveVoxelLayers = {
  mesh: boolean;
  pointCloud: boolean;
  scanPath: boolean;
  footprint: boolean;
  drone: boolean;
};

const COLORS = {
  mesh: "rgba(45, 161, 255, 0.72)",
  point_cloud: "rgba(92, 214, 148, 0.82)",
  occupancy: "rgba(255, 185, 80, 0.72)",
  esdf: "rgba(174, 116, 255, 0.58)",
  costmap: "rgba(255, 102, 102, 0.58)",
};

function project(
  point: [number, number, number],
  width: number,
  height: number,
): [number, number] {
  const scale = Math.min(width, height) / 18;
  return [
    width / 2 + (point[0] - point[1]) * scale,
    height * 0.58 + (point[0] + point[1]) * scale * 0.42 - point[2] * scale,
  ];
}

function drawScene(
  canvas: HTMLCanvasElement,
  state: WarehouseLiveVoxelMapState,
  layers: LiveVoxelLayers,
) {
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) return;
  const width = canvas.clientWidth || 1;
  const height = canvas.clientHeight || 1;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = "#071113";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(255,255,255,0.08)";
  for (let i = -12; i <= 12; i += 1) {
    const a = project([i, -12, 0], width, height);
    const b = project([i, 12, 0], width, height);
    const c = project([-12, i, 0], width, height);
    const d = project([12, i, 0], width, height);
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.moveTo(c[0], c[1]);
    ctx.lineTo(d[0], d[1]);
    ctx.stroke();
  }

  if (layers.footprint) {
    ctx.strokeStyle = "rgba(255,255,255,0.38)";
    ctx.strokeRect(28, 24, width - 56, height - 48);
  }

  for (const chunk of toRenderChunks(state.chunks)) {
    if (chunk.kind === "point_cloud" && !layers.pointCloud) continue;
    if (chunk.kind !== "point_cloud" && !layers.mesh) continue;
    const [x, y] = project(chunk.center, width, height);
    if (x < -80 || x > width + 80 || y < -80 || y > height + 80) continue;
    const px = Math.max(3, Math.min(28, (chunk.size[0] + chunk.size[1]) * 8));
    ctx.fillStyle = COLORS[chunk.kind];
    ctx.globalAlpha = chunk.hasGeometry ? 1 : 0.46;
    ctx.fillRect(x - px / 2, y - px / 2, px, px);
    ctx.globalAlpha = 1;
  }

  if (layers.scanPath && state.scanPath.length > 0) {
    ctx.strokeStyle = "#ffb020";
    ctx.lineWidth = 2;
    ctx.beginPath();
    state.scanPath.forEach((pose, index) => {
      const [x, y] = project([pose.x_m, pose.y_m, pose.z_m], width, height);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  if (layers.drone) {
    const [x, y] = project(
      poseToVec3(state.latestUpdate?.pose ?? null),
      width,
      height,
    );
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.fill();
  }
}

export function WarehouseLiveVoxelScene({
  state,
  layers,
}: {
  state: WarehouseLiveVoxelMapState;
  layers: LiveVoxelLayers;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    let frame = window.requestAnimationFrame(() => {
      if (canvasRef.current) drawScene(canvasRef.current, state, layers);
    });
    const resize = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        if (canvasRef.current) drawScene(canvasRef.current, state, layers);
      });
    };
    window.addEventListener("resize", resize);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
    };
  }, [layers, state]);

  return (
    <Box sx={{ height: 420, bgcolor: "#071113", position: "relative" }}>
      <canvas
        ref={canvasRef}
        data-testid="warehouse-live-voxel-map"
        style={{ width: "100%", height: "100%", display: "block" }}
      />
    </Box>
  );
}
