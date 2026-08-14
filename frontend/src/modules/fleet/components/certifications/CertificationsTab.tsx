import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { ActionIconButton } from "../../../../shared/ui/ActionIconButton";
import { PageSection } from "../../../../shared/layout/PageLayout";
import { fetchCertifications } from "../../api/fleetApi";
import { FLEET_CERTIFICATIONS_QUERY_KEY } from "../../fleetPageConstants";
import { AddCertDialog } from "./AddCertDialog";
import { CertRow } from "./CertRow";

export function CertificationsTab() {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);

  const { data: certs = [], isLoading } = useQuery({
    queryKey: FLEET_CERTIFICATIONS_QUERY_KEY,
    queryFn: () => fetchCertifications(),
  });

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: FLEET_CERTIFICATIONS_QUERY_KEY });

  return (
    <PageSection
      title="Certifications"
      description="Regulatory and authority certifications tied to this fleet."
      action={
        <ActionIconButton
          variant="add"
          title="Add Certification"
          color="primary"
          onClick={() => setAddOpen(true)}
        />
      }
    >
      {isLoading && <Typography color="text.secondary">Loading certifications…</Typography>}
      {!isLoading && certs.length === 0 && (
        <Paper variant="outlined" sx={{ p: 4, borderRadius: 3, textAlign: "center" }}>
          <Typography color="text.secondary">
            No certifications on record. Add one to track regulatory compliance.
          </Typography>
        </Paper>
      )}
      <Stack spacing={1.5}>
        {certs.map((cert) => (
          <CertRow key={cert.id} cert={cert} />
        ))}
      </Stack>
      <AddCertDialog open={addOpen} onClose={() => setAddOpen(false)} onCreated={refresh} />
    </PageSection>
  );
}
