import { useEffect, useState } from "react";
import { Alert, Box, Container, Divider, Paper, Tab, Tabs } from "@mui/material";
import { useBlocker, useNavigate } from "react-router-dom";
import { getToken } from "../../../modules/session";
import { AiSettingsPanel } from "../components/AiSettingsPanel";
import {
  SettingsPageActions,
} from "../components/SettingsPageChrome";
import { SettingsUnsavedBar } from "../components/SettingsUnsavedBar";
import { SettingsAlertsTab } from "../components/tabs/SettingsAlertsTab";
import { SettingsCameraTab } from "../components/tabs/SettingsCameraTab";
import { SettingsCredentialsTab } from "../components/tabs/SettingsCredentialsTab";
import { SettingsHardwareTab } from "../components/tabs/SettingsHardwareTab";
import { SettingsPhotogrammetryTab } from "../components/tabs/SettingsPhotogrammetryTab";
import { SettingsPreflightTab } from "../components/tabs/SettingsPreflightTab";
import { SettingsProfileTab } from "../components/tabs/SettingsProfileTab";
import { SettingsRaspberryTab } from "../components/tabs/SettingsRaspberryTab";
import { SettingsTelemetryTab } from "../components/tabs/SettingsTelemetryTab";
import { useCurrentUserProfile } from "../hooks/useCurrentUserProfile";
import { useSettingsDocument } from "../hooks/useSettingsDocument";
import {
  SETTINGS_TAB_INDEX,
  SETTINGS_TAB_LABELS,
  type SettingsTabKey,
} from "../settingsTabs";

export default function SettingsPage({
  initialTab = "profile",
}: {
  initialTab?: SettingsTabKey;
}) {
  const token = getToken();
  const navigate = useNavigate();
  const [tab, setTab] = useState(SETTINGS_TAB_INDEX[initialTab] ?? 0);
  const settings = useSettingsDocument();
  const profile = useCurrentUserProfile();
  const blocker = useBlocker(settings.dirty);

  useEffect(() => {
    setTab(SETTINGS_TAB_INDEX[initialTab] ?? 0);
  }, [initialTab]);

  useEffect(() => {
    if (blocker.state !== "blocked") return;
    const leave = window.confirm(
      "You have unsaved settings changes. Leave this page and discard them?",
    );
    if (leave) {
      settings.discardSettings();
      blocker.proceed();
    } else {
      blocker.reset();
    }
    // discardSettings closes over latest doc helpers; blocker identity drives the prompt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blocker.state]);

  const selectSettingsTab = (value: number) => {
    setTab(value);
    if (value === SETTINGS_TAB_INDEX.ai) {
      navigate("/admin/settings/ai", { replace: true });
    } else if (value === SETTINGS_TAB_INDEX.hardware) {
      navigate("/admin/settings/hardware", { replace: true });
    } else if (value === SETTINGS_TAB_INDEX.profile) {
      navigate("/admin/settings", { replace: true });
    }
  };

  const tabPanelProps = {
    doc: settings.doc,
    update: settings.update,
  };

  return (
    <>
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper variant="outlined" sx={{ p: 0 }}>
          <Tabs
            value={tab}
            onChange={(_, value) => selectSettingsTab(value)}
            variant="scrollable"
            scrollButtons="auto"
            aria-label="Settings sections"
          >
            {SETTINGS_TAB_LABELS.map((label, index) => (
              <Tab
                key={label}
                id={`settings-tab-${index}`}
                aria-controls={`settings-tabpanel-${index}`}
                label={label}
              />
            ))}
          </Tabs>
          <Divider />

          <Box
            component="fieldset"
            disabled={settings.loading || settings.saving}
            aria-busy={settings.loading || settings.saving}
            sx={{ p: 3, m: 0, border: 0, minWidth: 0 }}
          >
            {settings.err && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {settings.err}
              </Alert>
            )}
            {settings.loading && (
              <Alert severity="info" sx={{ mb: 2 }}>
                Loading settings...
              </Alert>
            )}

            <Box
              role="tabpanel"
              id={`settings-tabpanel-${tab}`}
              aria-labelledby={`settings-tab-${tab}`}
            >
              {tab === SETTINGS_TAB_INDEX.profile && <SettingsProfileTab {...profile} />}
              {tab === SETTINGS_TAB_INDEX.telemetry && (
                <SettingsTelemetryTab
                  {...tabPanelProps}
                  onFileUpload={settings.handleFileUpload}
                />
              )}
              {tab === SETTINGS_TAB_INDEX.ai && (
                <AiSettingsPanel
                  ai={settings.doc.ai}
                  onAiFieldChange={(field, value) => settings.update("ai", field, value)}
                  onProfilesPersisted={settings.persistAiProfiles}
                />
              )}
              {tab === SETTINGS_TAB_INDEX.credentials && (
                <SettingsCredentialsTab
                  {...tabPanelProps}
                  token={token}
                  hasOrg={Boolean(profile.user?.org_id)}
                />
              )}
              {tab === SETTINGS_TAB_INDEX.hardware && (
                <SettingsHardwareTab {...tabPanelProps} />
              )}
              {tab === SETTINGS_TAB_INDEX.preflight && (
                <SettingsPreflightTab {...tabPanelProps} />
              )}
              {tab === SETTINGS_TAB_INDEX.alerts && (
                <SettingsAlertsTab {...tabPanelProps} />
              )}
              {tab === SETTINGS_TAB_INDEX.raspberry && (
                <SettingsRaspberryTab
                  {...tabPanelProps}
                  onFileUpload={settings.handleFileUpload}
                />
              )}
              {tab === SETTINGS_TAB_INDEX.camera && (
                <SettingsCameraTab {...tabPanelProps} />
              )}
              {tab === SETTINGS_TAB_INDEX.photogrammetry && (
                <SettingsPhotogrammetryTab {...tabPanelProps} />
              )}
            </Box>

            <SettingsPageActions
              loading={settings.loading}
              saving={settings.saving}
              dirty={settings.dirty}
              onReset={() => void settings.fetchSettings()}
              onSave={() => void settings.saveSettings()}
            />
          </Box>
        </Paper>
      </Container>
      <SettingsUnsavedBar
        dirty={settings.dirty}
        saving={settings.saving}
        loading={settings.loading}
        onDiscard={settings.discardSettings}
        onSave={() => void settings.saveSettings()}
      />
    </>
  );
}
