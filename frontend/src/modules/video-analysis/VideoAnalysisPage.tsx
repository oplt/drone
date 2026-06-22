import { Container } from "@mui/material";
import { VideoAnalysisPanel } from "./VideoAnalysisPanel";

export default function VideoAnalysisPage() {
  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <VideoAnalysisPanel />
    </Container>
  );
}
