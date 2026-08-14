import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ActionIconButton } from "../../../../shared/ui/ActionIconButton";
import { PageSection } from "../../../../shared/layout/PageLayout";
import { fetchDevices } from "../../api/fleetApi";
import { FLEET_DEVICES_QUERY_KEY } from "../../fleetPageConstants";
import { AddDeviceDialog } from "./AddDeviceDialog";
import { DeviceRow } from "./DeviceRow";

export function DeviceReadinessTab() {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const { data: devices = [], isLoading } = useQuery({
    queryKey: FLEET_DEVICES_QUERY_KEY,
    queryFn: () => fetchDevices(),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: FLEET_DEVICES_QUERY_KEY });

  return (
    <PageSection
      title="Device Readiness"
      description="Airworthiness status and inspection schedule for each device in the fleet."
      action={
        <ActionIconButton
          variant="add"
          title="Add Device"
          color="primary"
          onClick={() => setAddOpen(true)}
        />
      }
    >
      {isLoading && <Typography color="text.secondary">Loading devices…</Typography>}
      {!isLoading && devices.length === 0 && (
        <Paper variant="outlined" sx={{ p: 4, borderRadius: 3, textAlign: "center" }}>
          <Typography color="text.secondary">
            No devices on record. Add one to track airworthiness and inspection status.
          </Typography>
        </Paper>
      )}
      <Stack spacing={1.5}>
        {devices.map((device) => (
          <DeviceRow key={device.id} device={device} />
        ))}
      </Stack>
      <AddDeviceDialog open={addOpen} onClose={() => setAddOpen(false)} onCreated={refresh} />
    </PageSection>
  );
}
