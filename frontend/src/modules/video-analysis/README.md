# Video Analysis Frontend Module

Install:

```bash
npm install @tanstack/react-query @mui/x-data-grid maplibre-gl
npm install @mui/material @mui/icons-material @emotion/react @emotion/styled
```

Route:

```tsx
import VideoAnalysisPage from '@/modules/video-analysis';
<Route path="/dashboard/video-analysis" element={<VideoAnalysisPage />} />
```

Expected backend routes:

- `POST /video-analysis/videos`
- `POST /video-analysis/videos/:videoId/analyze`
- `GET /video-analysis/jobs/:jobId`
- `GET /video-analysis/jobs/:jobId/detections`

For persisted video playback after refresh, add a backend streaming route such as:

This UI previews the selected local video immediately, polls job progress, and overlays detections
while analysis results are committed. Map points appear only when backend telemetry matching
provides coordinates.
