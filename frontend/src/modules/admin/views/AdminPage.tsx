import { useState } from "react";
import { Box, Paper, Tab, Tabs, Typography } from "@mui/material";

import { AdminDiagnosticsTab } from "../components/AdminDiagnosticsTab";
import { AdminExportJobsTab } from "../components/AdminExportJobsTab";
import { AdminMappingJobsTab } from "../components/AdminMappingJobsTab";
import { AdminOrgsTab } from "../components/AdminOrgsTab";
import { AdminUsersTab } from "../components/AdminUsersTab";
import { AdminWorkerHealthTab } from "../components/AdminWorkerHealthTab";
import { ADMIN_TABS } from "../adminTypes";

export default function AdminPage() {
  const [tab, setTab] = useState(0);

  return (
    <Box sx={{ p: { xs: 2, md: 3 } }}>
      <Typography variant="h5" fontWeight={700} sx={{ mb: 2 }}>
        Admin Console
      </Typography>
      <Tabs
        value={tab}
        onChange={(_, value) => setTab(value)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}
      >
        {ADMIN_TABS.map((label) => (
          <Tab key={label} label={label} />
        ))}
      </Tabs>

      <Paper variant="outlined" sx={{ p: 2, overflow: "auto" }}>
        {tab === 0 && <AdminUsersTab />}
        {tab === 1 && <AdminOrgsTab />}
        {tab === 2 && <AdminMappingJobsTab />}
        {tab === 3 && <AdminExportJobsTab />}
        {tab === 4 && <AdminWorkerHealthTab />}
        {tab === 5 && <AdminDiagnosticsTab />}
      </Paper>
    </Box>
  );
}
