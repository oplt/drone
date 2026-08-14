import { useState } from "react";
import Box from "@mui/material/Box";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import PageLayout from "../../../shared/layout/PageLayout";
import { CertificationsTab } from "../components/certifications/CertificationsTab";
import { DeviceReadinessTab } from "../components/devices/DeviceReadinessTab";
import { FleetOverviewTab } from "../components/FleetOverviewTab";
import { useFleetOverviewSession } from "../hooks/useFleetOverviewSession";

export default function FleetPage() {
  const [tab, setTab] = useState(0);
  const overview = useFleetOverviewSession();
  const system = overview.system;

  return (
    <PageLayout
      eyebrow="Fleet"
      title="Fleet connectivity and mission readiness"
      description="Watch link quality, battery reserve, and recent missions from one control surface."
      metrics={[
        {
          label: "Telemetry stream",
          value: system?.telemetry_running ? "Running" : "Stopped",
          caption: "Live backend state",
        },
        {
          label: "MAVLink",
          value: system?.mavlink_connected ? "Connected" : "Idle",
          caption: "Vehicle link state",
        },
        {
          label: "Active clients",
          value: `${system?.active_connections ?? 0}`,
          caption: "Current operator sessions",
        },
      ]}
    >
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
        <Tabs value={tab} onChange={(_, value) => setTab(value)}>
          <Tab label="Overview" />
          <Tab label="Certifications" />
          <Tab label="Device Readiness" />
        </Tabs>
      </Box>
      {tab === 0 && <FleetOverviewTab session={overview} />}
      {tab === 1 && <CertificationsTab />}
      {tab === 2 && <DeviceReadinessTab />}
    </PageLayout>
  );
}
