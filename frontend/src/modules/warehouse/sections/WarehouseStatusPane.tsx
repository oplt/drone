import { MissionVideoPanel } from "../../mission-runtime";
import type { ComponentProps } from "react";

type WarehouseStatusPaneProps = ComponentProps<typeof MissionVideoPanel>;

export function WarehouseStatusPane(props: WarehouseStatusPaneProps) {
  return <MissionVideoPanel {...props} />;
}
