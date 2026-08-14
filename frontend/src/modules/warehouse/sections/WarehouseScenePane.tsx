import type { RefObject } from "react";
import { WarehouseViewerSection } from "../components/WarehouseViewerSection";
import type { ComponentProps } from "react";

type WarehouseScenePaneProps = {
  sectionRef: RefObject<HTMLDivElement | null>;
  selectorProps: ComponentProps<typeof WarehouseViewerSection>["selectorProps"];
  showViewer: boolean;
  replayMode: boolean;
  viewerProps: ComponentProps<typeof WarehouseViewerSection>["viewerProps"];
};

export function WarehouseScenePane({
  sectionRef,
  selectorProps,
  showViewer,
  replayMode,
  viewerProps,
}: WarehouseScenePaneProps) {
  return (
    <WarehouseViewerSection
      sectionRef={sectionRef}
      selectorProps={selectorProps}
      showViewer={showViewer}
      replayMode={replayMode}
      viewerProps={viewerProps}
    />
  );
}
