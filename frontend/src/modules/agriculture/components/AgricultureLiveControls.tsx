import { Alert, Button, ButtonGroup, Stack, Typography } from "@mui/material";
import { useConfirm } from "../../../shared/ui/ConfirmContext";
import { useAgricultureRuntimeCommand } from "../hooks";

type Command = "pause" | "resume" | "rth" | "abort";

export function AgricultureLiveControls({ flightId, state, online, sequence }: { flightId: string; state?: string | null; online: boolean; sequence?: number }) {
  const { confirm } = useConfirm();
  const command = useAgricultureRuntimeCommand();
  const issue = async (value: Command) => {
    if (!online) return;
    if (value === "abort" || value === "rth") {
      const accepted = await confirm({ title: value === "abort" ? "Abort agriculture flight?" : "Return to home?", description: "This safety-critical command is sent to the connected drone and audited.", confirmLabel: value === "abort" ? "Abort flight" : "Return home", confirmColor: value === "abort" ? "error" : "warning" });
      if (!accepted) return;
    }
    await command.mutateAsync({ flightId, command: value, expectedSequence: sequence });
  };
  return <Stack component="section" aria-labelledby="agri-live-controls" spacing={1}>
    <Typography id="agri-live-controls" variant="subtitle2">Flight controls</Typography>
    {!online ? <Alert severity="warning">Controls locked while the live link is unavailable. Last-known state remains visible.</Alert> : null}
    {command.isError ? <Alert severity="error">Command was not accepted. Verify the drone link and retry.</Alert> : null}
    {command.data ? <Alert severity={command.data.accepted ? "success" : "warning"} role="status">{command.data.message}</Alert> : null}
    <ButtonGroup variant="outlined" aria-label="Agriculture flight commands" sx={{ "& .MuiButton-root": { minHeight: 44 } }}>
      <Button onClick={() => void issue("pause")} disabled={!online || command.isPending || !["airborne", "running", "resumed"].includes(state ?? "")} aria-label="Pause agriculture flight">Pause</Button>
      <Button onClick={() => void issue("resume")} disabled={!online || command.isPending || state !== "paused"} aria-label="Resume agriculture flight">Resume</Button>
      <Button color="warning" onClick={() => void issue("rth")} disabled={!online || command.isPending || !["airborne", "running", "resumed"].includes(state ?? "")} aria-label="Return agriculture drone to home">Return home</Button>
      <Button color="error" onClick={() => void issue("abort")} disabled={!online || command.isPending || ["completed", "aborted", "failed"].includes(state ?? "")} aria-label="Abort agriculture flight">Abort</Button>
    </ButtonGroup>
  </Stack>;
}
