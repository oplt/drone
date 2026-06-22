import {
  MapShapeActionPopover,
  type MapShapeActionVariant,
} from "./MapShapeActionPopover";
import type { WorkflowFieldBoundaryVm } from "../hooks/useWorkflowFieldBoundary";

export function MissionMapBoundaryPrompt({
  variant,
  boundary,
}: {
  variant: MapShapeActionVariant;
  boundary: Pick<
    WorkflowFieldBoundaryVm,
    | "fieldName"
    | "setFieldName"
    | "selectedFieldId"
    | "savingField"
    | "shapePrompt"
    | "saveFromShapePrompt"
  >;
}) {
  return (
    <MapShapeActionPopover
      open={boundary.shapePrompt.open}
      variant={variant}
      name={boundary.fieldName}
      saving={boundary.savingField}
      isUpdate={boundary.selectedFieldId != null}
      onNameChange={boundary.setFieldName}
      onSave={() => void boundary.saveFromShapePrompt()}
      onDismiss={boundary.shapePrompt.closePrompt}
    />
  );
}
