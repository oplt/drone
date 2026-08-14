import { Box, FormControlLabel, Switch, Typography } from "@mui/material";
import type { PatrolGridParams } from "../../types";
import { AI_TASKS_SX, PARAM_FIELD_SX, PARAM_FULL_ROW_SX } from "./patrolParamsLayout";
import type { PatrolParamsSetter } from "./patrolParamsTypes";

const AI_TASK_OPTIONS: [PatrolGridParams["ai_tasks"][number], string][] = [
  ["intruder_detection", "Intruder detection"],
  ["vehicle_detection", "Vehicle detection"],
  ["fence_breach_detection", "Fence breach detection"],
  ["motion_detection", "Motion detection"],
];

type PatrolAiTasksSectionProps = {
  gridParams: PatrolGridParams;
  setGridParams: PatrolParamsSetter;
};

export function PatrolAiTasksSection({
  gridParams,
  setGridParams,
}: PatrolAiTasksSectionProps) {
  return (
    <Box sx={PARAM_FULL_ROW_SX}>
      <Typography
        variant="caption"
        sx={{ color: "text.secondary", display: "block", mb: 0.75 }}
      >
        AI Tasks During Flight
      </Typography>
      <Box sx={AI_TASKS_SX}>
        {AI_TASK_OPTIONS.map(([task, label]) => {
          const checked = gridParams.ai_tasks.includes(task);
          return (
            <FormControlLabel
              key={task}
              control={
                <Switch
                  size="small"
                  checked={checked}
                  onChange={(e) => {
                    setGridParams((p) => {
                      if (e.target.checked) {
                        if (p.ai_tasks.includes(task)) return p;
                        return { ...p, ai_tasks: [...p.ai_tasks, task] };
                      }
                      const next = p.ai_tasks.filter((t) => t !== task);
                      return {
                        ...p,
                        ai_tasks: next.length > 0 ? next : p.ai_tasks,
                      };
                    });
                  }}
                />
              }
              label={<Typography variant="caption">{label}</Typography>}
              sx={PARAM_FIELD_SX.s}
            />
          );
        })}
      </Box>
    </Box>
  );
}
