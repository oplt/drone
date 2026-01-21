import time
import os
from typing import Iterator, Union, Optional
import cv2
from datetime import datetime
import logging

def _is_rtsp(s: str) -> bool:
    return isinstance(s, str) and s.lower().startswith(("rtsp://", "rtsps://", "udp://", "tcp://", "http://", "https://"))

class DroneVideoStream:
    """
    Enhanced video streaming for drone applications with:
      - Raspberry Pi 5 camera support (USB, CSI, network)
      - Auto backend selection (V4L2 for /dev/video*, FFMPEG for RTSP/HTTP/file)
      - Warm-up with retries and connection monitoring
      - Multi-source probing when a source fails
      - Optional video recording with timestamp
      - Fallback file support when live source is unavailable
      - Connection health monitoring for drone applications
    """
    def __init__(
            self,
            source: Union[int, str, None] = 0,
            width: int = 640,
            height: int = 480,
            fps: int = 30,
            open_timeout_s: float = 5.0,
            probe_indices: int = 5,
            fallback_file: str | None = None,
            fps_limit: float | None = None,  # throttle frame rate to save CPU/LLM cost (None = no limit)
            enable_recording: bool = False,
            recording_path: str = "./recordings/",
            recording_format: str = "mp4",
            use_raspberry_pi: bool = False,
            pi_host: str = None,
    ):
        self.fps_limit = fps_limit
        self._last_ts = 0.0
        self.cap = None
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps
        self.enable_recording = enable_recording
        self.recording_path = recording_path
        self.recording_format = recording_format
        self.video_writer = None
        self.recording_filename = None
        self.connection_healthy = False
        self.last_frame_time = 0
        self.frame_count = 0
        self.use_raspberry_pi = use_raspberry_pi
        self.pi_host = pi_host

        if use_raspberry_pi and pi_host:
            source = f"http://{pi_host}:5000/video_feed"
        
        # Ensure recording directory exists
        if self.enable_recording:
            os.makedirs(self.recording_path, exist_ok=True)

        # 1) Try the requested source
        if source is not None:
            self.cap = self._open_source(source, width, height, fps, open_timeout_s)

        # 2) If that failed AND we were given an int (or None), probe other /dev/videoN
        if self.cap is None and (source is None or isinstance(source, int)):
            for idx in range(0, probe_indices + 1):
                try:
                    self.cap = self._open_source(idx, width, height, fps, open_timeout_s)
                    logging.info(f"[Video] Probed working camera at index {idx}")
                    break
                except RuntimeError:
                    continue

        # 3) If still no live source, try fallback file if provided
        if self.cap is None and fallback_file and os.path.exists(fallback_file):
            try:
                self.cap = self._open_source(fallback_file, width, height, fps, open_timeout_s)
                logging.info(f"[Video] Using fallback file: {fallback_file}")
            except RuntimeError:
                pass

        if self.cap is None:
            raise RuntimeError(f"Camera not ready: source={source}")
        
        # Start recording if enabled
        if self.enable_recording:
            self._start_recording()

    def _open_source(self, source, width, height, fps, open_timeout_s):
        if isinstance(source, int):
            # Try V4L2 first for Linux USB cameras (Raspberry Pi 5)
            cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
            if not cap.isOpened():
                # Fallback to default backend
                cap = cv2.VideoCapture(source)
        elif _is_rtsp(source) or isinstance(source, str):
            # Prefer FFMPEG backend for RTSP/HTTP/file
            cap = cv2.VideoCapture(source, cv2.CAP_FFMPEG)
            # Helpful FFmpeg options for low-latency RTSP (ignored if not RTSP)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FPS, fps)
        else:
            cap = cv2.VideoCapture(source)

        # Try to set resolution and FPS (may be ignored by RTSP)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)

        # Warm-up / readiness check
        t0 = time.time()
        ok, _ = cap.read()
        while not ok and (time.time() - t0) < open_timeout_s:
            time.sleep(0.2)
            ok, _ = cap.read()
        if not ok:
            cap.release()
            raise RuntimeError(f"OpenCV source failed: {source}")
        
        self.connection_healthy = True
        return cap

    def _start_recording(self):
        """Start video recording with timestamp (or resume with existing filename)"""
        if not self.enable_recording or self.cap is None:
            return
        
        # Use existing filename if resuming recording, otherwise create new one
        if not self.recording_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.recording_filename = f"drone_video_{timestamp}.{self.recording_format}"
        
        full_path = os.path.join(self.recording_path, self.recording_filename)
        
        # Get actual video properties from camera
        actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
        
        if actual_fps <= 0:
            actual_fps = self.fps
            
        # Define codec based on format
        if self.recording_format == "mp4":
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        elif self.recording_format == "avi":
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
        else:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            
        self.video_writer = cv2.VideoWriter(
            full_path, fourcc, actual_fps, (actual_width, actual_height)
        )
        
        if not self.video_writer.isOpened():
            logging.error(f"Failed to open video writer for {full_path}")
            self.video_writer = None
        else:
            logging.info(f"Started video recording: {full_path}")

    def _stop_recording(self):
        """Stop video recording"""
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
            if self.recording_filename:
                logging.info(f"Stopped video recording: {self.recording_filename}")

    def _check_connection_health(self):
        """Monitor connection health for drone applications without consuming frames"""
        if self.cap is None:
            self.connection_healthy = False
            return False
        
        # Check if capture is opened without reading a frame
        if not self.cap.isOpened():
            self.connection_healthy = False
            logging.warning("Video stream capture not opened")
            return False
        
        # Check frame rate health based on last frame time (non-intrusive)
        now = time.time()
        if self.last_frame_time > 0:
            frame_interval = now - self.last_frame_time
            expected_interval = 1.0 / self.fps if self.fps > 0 else 0.033  # Default to ~30fps
            if frame_interval > expected_interval * 3:  # Allow tolerance for occasional slow frames
                logging.warning(f"Video stream frame rate degraded: {1.0/frame_interval:.1f} fps (expected: {self.fps})")
                # Don't mark as unhealthy for occasional slow frames, only if consistently slow
                if frame_interval > expected_interval * 5:
                    self.connection_healthy = False
                    return False
        
        # If we haven't received frames in a while, mark as potentially unhealthy
        if self.last_frame_time > 0 and (now - self.last_frame_time) > 5.0:  # 5 seconds without frames
            self.connection_healthy = False
            logging.warning("No frames received for 5+ seconds")
            return False
        
        self.connection_healthy = True
        return True

    def frames(self) -> Iterator[tuple[int, any]]:
        """Generate video frames with health monitoring"""
        consecutive_failures = 0
        max_consecutive_failures = 10  # Allow up to 10 consecutive failures before giving up
        
        while True:
            # Check connection health periodically (non-intrusive, doesn't consume frames)
            if self.frame_count % 60 == 0:  # Check every 60 frames (less frequent)
                if not self._check_connection_health():
                    logging.warning("Video stream connection unhealthy, attempting to reconnect...")
                    # Try to reconnect
                    self._reconnect()
                    if self.cap is None:
                        break
                    # Continue to next iteration to try reading frame
            
            ok, frame = self.cap.read()
            if not ok:
                consecutive_failures += 1
                
                # For files, try to loop from start
                if isinstance(self.source, str) and not _is_rtsp(self.source):
                    # Only try to loop if it's a file source, not network stream
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = self.cap.read()
                
                if not ok:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        logging.error(f"Failed to read frame from video source after {consecutive_failures} consecutive attempts - stopping video stream")
                        break
                    # Log warning only occasionally to reduce spam
                    if consecutive_failures % 5 == 0:
                        logging.warning(f"Failed to read frame ({consecutive_failures}/{max_consecutive_failures} consecutive failures)")
                    time.sleep(0.1)  # Small delay before retry
                    continue  # Try reading next frame instead of breaking
            
            # Reset failure counter on success
            consecutive_failures = 0

            # Record frame if recording is enabled
            if self.video_writer and self.video_writer.isOpened():
                self.video_writer.write(frame)

            # FPS throttle
            if self.fps_limit:
                now = time.time()
                min_dt = 1.0 / float(self.fps_limit)
                if now - self._last_ts < min_dt:
                    # Busy-wait light sleep to avoid extra CPU
                    time.sleep(min_dt - (now - self._last_ts))
                self._last_ts = time.time()

            self.frame_count += 1
            yield frame.shape[1], frame  # (width, frame)

    def _reconnect(self):
        """Attempt to reconnect to video source while preserving recording"""
        try:
            # Preserve recording state and filename before reconnecting
            was_recording = self.video_writer is not None and self.video_writer.isOpened()
            preserved_filename = self.recording_filename
            
            if self.cap:
                self.cap.release()
            
            # Stop recording temporarily (will restart with same filename)
            if was_recording:
                self._stop_recording()
            
            # Wait a bit before reconnecting
            time.sleep(1.0)
            
            # Try to reconnect
            self.cap = self._open_source(self.source, self.width, self.height, self.fps, 5.0)
            if self.cap and self.cap.isOpened():
                logging.info("Successfully reconnected to video source")
                # Restart recording with preserved filename if it was active
                if was_recording:
                    # Restore the filename to continue recording
                    self.recording_filename = preserved_filename
                    self._start_recording()
                    logging.info(f"Resumed recording to existing file: {preserved_filename}")
            else:
                logging.error("Failed to reconnect to video source")
                # If reconnection failed but we were recording, try to restart recording
                if was_recording and self.enable_recording:
                    self.recording_filename = preserved_filename
                    logging.warning("Reconnection failed, will retry recording when connection restored")
                
        except Exception as e:
            logging.error(f"Error during video reconnection: {e}")
            # Try to preserve recording state even on error
            if was_recording and self.enable_recording:
                self.recording_filename = preserved_filename

    def get_connection_status(self) -> dict:
        """Get current connection status and statistics"""
        return {
            "healthy": self.connection_healthy,
            "frame_count": self.frame_count,
            "fps": self.fps,
            "resolution": f"{self.width}x{self.height}",
            "recording": self.video_writer is not None and self.video_writer.isOpened(),
            "recording_file": self.recording_filename
        }

    def close(self):
        """Clean up video resources"""
        try:
            self._stop_recording()
            if self.cap:
                self.cap.release()
        except Exception as e:
            logging.error(f"Error closing video stream: {e}")

# Backward compatibility alias
VideoStream = DroneVideoStream
