import type { SettingsDoc, SettingsSection } from "../settingsTypes";

export type SettingsFieldUpdater = (
  section: SettingsSection,
  field: string,
  value: unknown,
) => void;

export type SettingsTabPanelProps = {
  doc: SettingsDoc;
  update: SettingsFieldUpdater;
};

export type SettingsFileUploadHandler = (
  section: SettingsSection,
  field: string,
) => (event: React.ChangeEvent<HTMLInputElement>) => Promise<void>;

export type SettingsFileUploadTabProps = SettingsTabPanelProps & {
  onFileUpload: SettingsFileUploadHandler;
};
