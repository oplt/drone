import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from "@mui/material";

type Props = {
  open: boolean;
  message: string | null;
  expectedRevision: number;
  currentRevision: number;
  onReload: () => void;
  onDownload: () => void;
  onOverwrite: () => void;
};

export function LabelingConflictDialog({
  open,
  message,
  expectedRevision,
  currentRevision,
  onReload,
  onDownload,
  onOverwrite,
}: Props) {
  return (
    <Dialog
      open={open}
      aria-labelledby="labeling-conflict-title"
      aria-describedby="labeling-conflict-description"
    >
      <DialogTitle id="labeling-conflict-title">
        Annotation revision conflict
      </DialogTitle>
      <DialogContent>
        <DialogContentText id="labeling-conflict-description">
          {message} Your draft used revision {expectedRevision}; the server is now
          revision {currentRevision}. Choose how to resolve the conflict before
          continuing.
        </DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button autoFocus onClick={onReload}>
          Reload server version
        </Button>
        <Button onClick={onDownload}>Download local copy</Button>
        <Button color="warning" variant="contained" onClick={onOverwrite}>
          Overwrite with my draft
        </Button>
      </DialogActions>
    </Dialog>
  );
}
