import { Container } from "@mui/material";
import { AgricultureAccessibilityBoundary } from "../agriculture/components/AgricultureAccessibilityBoundary";
import { VideoAnalysisPanel } from "./VideoAnalysisPanel";

export default function VideoAnalysisPage() {
  return (
    <AgricultureAccessibilityBoundary>
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <VideoAnalysisPanel />
      </Container>
    </AgricultureAccessibilityBoundary>
  );
}
