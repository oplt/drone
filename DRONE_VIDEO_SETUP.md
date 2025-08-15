# Drone Video Streaming Setup Guide for Raspberry Pi 5

This guide explains how to configure and use the enhanced video streaming capabilities for your drone project on Raspberry Pi 5.

## Overview

The enhanced video system supports:
- **USB Cameras**: Direct connection to Raspberry Pi 5
- **CSI Cameras**: Raspberry Pi Camera Module
- **Network Cameras**: RTSP, HTTP, or TCP streams
- **Automatic Recording**: Timestamped video files
- **Health Monitoring**: Connection status and frame rate monitoring
- **Fallback Support**: Backup video sources when live stream fails

## Environment Configuration

Create a `.env` file in your project root with these video-related settings:

```bash
# Drone Video Streaming Configuration
DRONE_VIDEO_ENABLED=true

# Video source configuration
# For USB camera on Raspberry Pi 5: use 0, 1, 2, etc.
# For RTSP stream: use "rtsp://192.168.1.100:554/stream"
# For network camera: use "http://192.168.1.100:8080/video"
DRONE_VIDEO_SOURCE=0

# Video quality settings
DRONE_VIDEO_WIDTH=640
DRONE_VIDEO_HEIGHT=480
DRONE_VIDEO_FPS=30

# Connection timeout (seconds)
DRONE_VIDEO_TIMEOUT=5.0

# Fallback video file if live stream fails (optional)
# DRONE_VIDEO_FALLBACK=/path/to/fallback.mp4

# Video recording settings
DRONE_VIDEO_SAVE_STREAM=false
DRONE_VIDEO_SAVE_PATH=./recordings/
```

## Camera Setup Options

### 1. USB Camera (Recommended for Raspberry Pi 5)

```bash
# Check available USB cameras
ls /dev/video*

# Test camera with v4l2-ctl
sudo apt install v4l-utils
v4l2-ctl --list-devices

# Test camera with ffmpeg
ffmpeg -f v4l2 -i /dev/video0 -t 5 -f null -
```

**Configuration:**
```bash
DRONE_VIDEO_SOURCE=0
DRONE_VIDEO_WIDTH=640
DRONE_VIDEO_HEIGHT=480
DRONE_VIDEO_FPS=30
```

### 2. CSI Camera (Raspberry Pi Camera Module)

```bash
# Enable camera in raspi-config
sudo raspi-config

# Check camera status
vcgencmd get_camera

# Test camera
raspistill -o test.jpg
```

**Configuration:**
```bash
DRONE_VIDEO_SOURCE=0
DRONE_VIDEO_WIDTH=1920
DRONE_VIDEO_HEIGHT=1080
DRONE_VIDEO_FPS=30
```

### 3. Network Camera (RTSP/HTTP)

**For RTSP cameras:**
```bash
DRONE_VIDEO_SOURCE=rtsp://192.168.1.100:554/stream
DRONE_VIDEO_WIDTH=1280
DRONE_VIDEO_HEIGHT=720
DRONE_VIDEO_FPS=25
```

**For HTTP cameras:**
```bash
DRONE_VIDEO_SOURCE=http://192.168.1.100:8080/video
DRONE_VIDEO_WIDTH=640
DRONE_VIDEO_HEIGHT=480
DRONE_VIDEO_FPS=30
```

## Video Recording

Enable automatic video recording:

```bash
DRONE_VIDEO_SAVE_STREAM=true
DRONE_VIDEO_SAVE_PATH=./recordings/
```

Recordings will be saved with timestamps: `drone_video_20241201_143022.mp4`

## Health Monitoring

The system automatically monitors:
- Connection health
- Frame rate performance
- Recording status
- Error conditions

Monitor video health via MQTT:
```bash
mosquitto_sub -h localhost -t "drone/video/status" -v
```

## Troubleshooting

### Camera Not Detected

1. **Check device permissions:**
```bash
sudo usermod -a -G video $USER
# Reboot required
```

2. **Check kernel modules:**
```bash
lsmod | grep uvcvideo
sudo modprobe uvcvideo
```

3. **Test with OpenCV:**
```python
import cv2
cap = cv2.VideoCapture(0)
if cap.isOpened():
    print("Camera working")
    ret, frame = cap.read()
    if ret:
        print("Frame captured successfully")
    cap.release()
else:
    print("Camera not accessible")
```

### Poor Performance

1. **Reduce resolution:**
```bash
DRONE_VIDEO_WIDTH=320
DRONE_VIDEO_HEIGHT=240
```

2. **Lower frame rate:**
```bash
DRONE_VIDEO_FPS=15
```

3. **Check CPU usage:**
```bash
htop
```

### Network Camera Issues

1. **Test network connectivity:**
```bash
ping 192.168.1.100
telnet 192.168.1.100 554
```

2. **Test with ffmpeg:**
```bash
ffmpeg -i "rtsp://192.168.1.100:554/stream" -t 10 -f null -
```

## Advanced Configuration

### Multiple Camera Sources

For multiple cameras, you can modify the code to handle multiple video streams:

```python
# In orchestrator.py, create multiple video tasks
async def multi_camera_vision_task(self):
    tasks = []
    for camera_id in range(3):  # 3 cameras
        task = asyncio.create_task(self.process_camera(camera_id))
        tasks.append(task)
    await asyncio.gather(*tasks)
```

### Custom Video Processing

Extend the video processing pipeline:

```python
async def custom_vision_task(self):
    for _, frame in self.video.frames():
        # Custom preprocessing
        processed_frame = self.preprocess_frame(frame)
        
        # Object detection
        detections = await self.analyzer.detect_objects(processed_frame)
        
        # Custom post-processing
        results = self.post_process_detections(detections)
        
        # Publish results
        self.mqtt.publish("drone/custom_detections", results)
```

## Performance Optimization

### Raspberry Pi 5 Specific

1. **Enable hardware acceleration:**
```bash
# In /boot/config.txt
gpu_mem=128
dtoverlay=vc4-fkms-v3d
```

2. **Use USB 3.0 ports** for USB cameras

3. **Monitor temperature:**
```bash
vcgencmd measure_temp
```

4. **Optimize OpenCV:**
```bash
# Install optimized OpenCV
pip install opencv-python-headless
```

## Monitoring and Logging

### Video Status Dashboard

Monitor video health in real-time:

```bash
# Watch video status
watch -n 1 'mosquitto_sub -h localhost -t "drone/video/status" -C 1'

# Monitor warnings
mosquitto_sub -h localhost -t "drone/warnings" -v

# Check recordings
ls -la ./recordings/
```

### Log Analysis

```bash
# Filter video-related logs
grep "video\|camera" drone.log

# Monitor errors
tail -f drone.log | grep ERROR
```

## Security Considerations

1. **Network isolation** for drone video streams
2. **Authentication** for RTSP/HTTP cameras
3. **Encryption** for sensitive video data
4. **Access control** for recorded videos

## Support

For issues and questions:
1. Check the logs in `drone.log`
2. Monitor MQTT topics for error messages
3. Verify camera hardware compatibility
4. Test with simple OpenCV scripts first

## Example Configurations

### Basic USB Camera
```bash
DRONE_VIDEO_ENABLED=true
DRONE_VIDEO_SOURCE=0
DRONE_VIDEO_WIDTH=640
DRONE_VIDEO_HEIGHT=480
DRONE_VIDEO_FPS=30
DRONE_VIDEO_SAVE_STREAM=true
```

### High-Quality Recording
```bash
DRONE_VIDEO_ENABLED=true
DRONE_VIDEO_SOURCE=0
DRONE_VIDEO_WIDTH=1920
DRONE_VIDEO_HEIGHT=1080
DRONE_VIDEO_FPS=30
DRONE_VIDEO_SAVE_STREAM=true
DRONE_VIDEO_SAVE_PATH=/mnt/external/recordings/
```

### Network Camera
```bash
DRONE_VIDEO_ENABLED=true
DRONE_VIDEO_SOURCE=rtsp://admin:password@192.168.1.100:554/stream1
DRONE_VIDEO_WIDTH=1280
DRONE_VIDEO_HEIGHT=720
DRONE_VIDEO_FPS=25
DRONE_VIDEO_TIMEOUT=10.0
```
