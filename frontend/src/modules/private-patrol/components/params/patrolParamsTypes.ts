import type { Dispatch, SetStateAction } from "react";
import type { PatrolGridParams } from "../../types";
import type { ParamsTab } from "./patrolParamsLayout";

export type PatrolParamsSetter = Dispatch<SetStateAction<PatrolGridParams>>;

export type PatrolParamsFieldProps = {
  gridParams: PatrolGridParams;
  setGridParams: PatrolParamsSetter;
  activeTab: ParamsTab;
};
