import { useState } from "react";
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from "@mui/material";
import { useCreateVisionProject } from "../hooks/useVisionModels";
import type { CreateVisionProjectInput } from "../visionApi";

const CAPABILITIES: Array<{ id: CreateVisionProjectInput["capability_id"]; label: string }> = [
  { id: "object_detection", label: "Custom object detection" },
  { id: "stand_count", label: "Stand count" },
  { id: "weed_detection", label: "Weed detection" },
  { id: "crop_health", label: "Crop-health findings" },
  { id: "canopy_cover", label: "Canopy cover" },
  { id: "row_detection", label: "Crop rows" },
  { id: "standing_water", label: "Standing water" },
  { id: "fruit_counting", label: "Crop-specific fruit counting" },
  { id: "ripeness_classification", label: "Crop-specific ripeness" },
];

export function VisionProjectCreateDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const create = useCreateVisionProject();
  const [name, setName] = useState("");
  const [crop, setCrop] = useState("");
  const [description, setDescription] = useState("");
  const [capabilityId, setCapabilityId] = useState<CreateVisionProjectInput["capability_id"]>("object_detection");
  const [classes, setClasses] = useState(
    "ripe tomato, unripe tomato, damaged tomato",
  );
  const classList = classes
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const submit = async () => {
    await create.mutateAsync({
      name,
      crop,
      description: description || undefined,
      capability_id: capabilityId,
      classes: classList.map((className) => ({ name: className })),
    });
    onClose();
    setName("");
    setCrop("");
  };
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Create agricultural vision project</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1}>
          <TextField
            label="Project name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoFocus
          />
          <TextField
            label="Crop"
            value={crop}
            onChange={(event) => setCrop(event.target.value)}
          />
          <TextField
            select
            label="Agriculture capability"
            value={capabilityId}
            onChange={(event) => setCapabilityId(event.target.value as typeof capabilityId)}
            helperText="Deploying this project's model makes this analysis available."
          >
            {CAPABILITIES.map((capability) => (
              <MenuItem key={capability.id} value={capability.id}>{capability.label}</MenuItem>
            ))}
          </TextField>
          <TextField
            label="Description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            multiline
            minRows={2}
          />
          <TextField
            label="Classes (comma separated)"
            value={classes}
            onChange={(event) => setClasses(event.target.value)}
            helperText="Class names are fixed after the first dataset is created."
          />
          {create.error ? (
            <Alert severity="error">{create.error.message}</Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={
            !name.trim() ||
            !crop.trim() ||
            !classList.length ||
            create.isPending
          }
          onClick={() => void submit()}
        >
          Create project
        </Button>
      </DialogActions>
    </Dialog>
  );
}
