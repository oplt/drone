import { PatrolGridPatternFields } from "./PatrolGridPatternFields";
import { PatrolGridPresetChips } from "./PatrolGridPresetChips";
import { PatrolGridSpacingFields } from "./PatrolGridSpacingFields";
import { PatrolScheduleFields } from "./PatrolScheduleFields";
import { PatrolSpeedField } from "./PatrolSpeedField";
import type { PatrolParamsFieldProps } from "./patrolParamsTypes";

export function PatrolGridSurveillanceParamsFields({
  gridParams,
  setGridParams,
  activeTab,
}: PatrolParamsFieldProps) {
  return (
    <>
      <PatrolGridPresetChips setGridParams={setGridParams} />
      <PatrolSpeedField
        gridParams={gridParams}
        setGridParams={setGridParams}
        activeTab={activeTab}
      />
      <PatrolScheduleFields gridParams={gridParams} setGridParams={setGridParams} />
      <PatrolGridPatternFields gridParams={gridParams} setGridParams={setGridParams} />
      <PatrolGridSpacingFields gridParams={gridParams} setGridParams={setGridParams} />
    </>
  );
}
