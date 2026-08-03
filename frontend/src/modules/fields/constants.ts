export type FieldWorkflowScope =
  | "field_survey"
  | "photogrammetry"
  | "property_patrol"
  | "animal_farm"
  | "agriculture";

export const FIELD_WORKFLOW_SCOPES = {
  fieldSurvey: "field_survey",
  photogrammetry: "photogrammetry",
  propertyPatrol: "property_patrol",
  animalFarm: "animal_farm",
  agriculture: "agriculture",
} as const satisfies Record<string, FieldWorkflowScope>;
