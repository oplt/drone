import {
  Box,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import type { WarehouseSceneNode } from "../utils/warehouseLayoutScene";

export function WarehouseLayoutCanvas({
  nodes,
  selectedId,
  mode,
  onModeChange,
  onSelect,
}: {
  nodes: WarehouseSceneNode[];
  selectedId: string | null;
  mode: "2d" | "3d";
  onModeChange: (mode: "2d" | "3d") => void;
  onSelect: (id: string) => void;
}) {
  const project = (node: WarehouseSceneNode) => {
    const x = 300 + node.x * 18;
    const y = 210 - node.y * 18;
    return mode === "3d" ? { x: x + node.z * 8, y: y - node.z * 8 } : { x, y };
  };
  return (
    <Box sx={{ minWidth: 0 }}>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          mb: 1,
        }}
      >
        <Typography variant="body2" color="text.secondary">
          warehouse_map · metres
        </Typography>
        <ToggleButtonGroup
          exclusive
          size="small"
          value={mode}
          aria-label="Scene projection"
          onChange={(_, value) => value && onModeChange(value)}
        >
          <ToggleButton value="2d">2D</ToggleButton>
          <ToggleButton value="3d">3D</ToggleButton>
        </ToggleButtonGroup>
      </Box>
      <Box
        component="svg"
        viewBox="0 0 600 420"
        role="img"
        aria-label={`${mode.toUpperCase()} warehouse layout editor`}
        sx={{
          width: "100%",
          minHeight: 320,
          bgcolor: "action.hover",
          borderRadius: 1,
        }}
      >
        <path d="M20 210H580M300 20V400" stroke="currentColor" opacity="0.12" />
        {nodes.map((node) => {
          const point = project(node);
          const selected = selectedId === node.id;
          const width = Math.max(8, node.width * 14);
          const depth = Math.max(8, node.depth * 14);
          return (
            <g
              key={node.id}
              role="button"
              tabIndex={0}
              aria-label={`${node.kind} ${node.label}`}
              onClick={() => onSelect(node.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ")
                  onSelect(node.id);
              }}
              style={{ cursor: "pointer", outline: "none" }}
            >
              {mode === "3d" && (
                <rect
                  x={point.x - width / 2 + 5}
                  y={point.y - depth / 2 - node.height * 5}
                  width={width}
                  height={depth}
                  fill="currentColor"
                  opacity="0.12"
                />
              )}
              <rect
                x={point.x - width / 2}
                y={point.y - depth / 2}
                width={width}
                height={depth}
                rx="2"
                fill={
                  selected ? "var(--mui-palette-primary-main)" : "currentColor"
                }
                opacity={selected ? 0.78 : 0.38}
              />
              <text
                x={point.x}
                y={point.y - depth / 2 - 5}
                textAnchor="middle"
                fontSize="10"
              >
                {node.label}
              </text>
            </g>
          );
        })}
        {nodes.length === 0 && (
          <text
            x="300"
            y="210"
            textAnchor="middle"
            fontSize="14"
            opacity="0.65"
          >
            Add an aisle or safety zone to begin
          </text>
        )}
      </Box>
    </Box>
  );
}
