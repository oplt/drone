# Wireless Video Streaming Setup: Drone to PC

This guide explains how to set up wireless video streaming from your drone (Raspberry Pi 5) to your PC.

## 🚁 System Architecture

```
[Drone with Raspberry Pi 5 + Camera]
           ↓ (WiFi)
    [WiFi Access Point]
           ↓ (WiFi)
    [PC/Computer]
```

## 🔧 Drone Side Setup (Raspberry Pi 5)

### 1. **Install Required Packages**
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install video streaming packages
sudo apt install ffmpeg v4l-utils hostapd dnsmasq -y

# Install Python dependencies
pip install opencv-python flask aiortc
```

### 2. **Configure WiFi Access Point**
```bash
# Create WiFi configuration
sudo nano /etc/hostapd/hostapd.conf
```

**Add this content:**
```bash
interface=wlan0
ssid=Drone_Network
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=drone123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
```

### 3. **Configure Network Interface**
```bash
# Set static IP for drone
sudo nano /etc/dhcpcd.conf
```

**Add at the end:**
```bash
interface wlan0
static ip_address=192.168.4.1/24
nohook wpa_supplicant
```

### 4. **Configure DHCP Server**
```bash
sudo nano /etc/dnsmasq.conf
```

**Add:**
```bash
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
```

### 5. **Enable Services**
```bash
# Enable hostapd and dnsmasq
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl enable dnsmasq

# Reboot to apply changes
sudo reboot
```

### 6. **Start Video Streaming Server**
```bash
# Create streaming script
nano ~/start_video_stream.sh
```

**Add this content:**
```bash
#!/bin/bash
# Start RTSP streaming server
ffmpeg -f v4l2 -i /dev/video0 \
       -c:v libx264 -preset ultrafast \
       -tune zerolatency \
       -f rtsp rtsp://0.0.0.0:8554/stream &

# Start HTTP web interface
python3 ~/video_web_server.py &

echo "Video streaming started!"
echo "RTSP: rtsp://192.168.4.1:8554/stream"
echo "Web: http://192.168.4.1:8080"
```

### 7. **Create Web Video Server**
```bash
nano ~/video_web_server.py
```

**Add this content:**
```python
#!/usr/bin/env python3
from flask import Flask, Response, render_template_string
import cv2
import threading
import time

app = Flask(__name__)

# Global variable for camera
camera = None
frame_buffer = None
lock = threading.Lock()

def get_camera():
    global camera
    if camera is None:
        camera = cv2.VideoCapture(0)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_FPS, 30)
    return camera

def generate_frames():
    global frame_buffer
    while True:
        with lock:
            if frame_buffer is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_buffer + b'\r\n')
        time.sleep(0.033)  # ~30 FPS

def camera_thread():
    global frame_buffer
    while True:
        try:
            cap = get_camera()
            ret, frame = cap.read()
            if ret:
                # Encode frame to JPEG
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    with lock:
                        frame_buffer = buffer.tobytes()
            time.sleep(0.033)  # ~30 FPS
        except Exception as e:
            print(f"Camera error: {e}")
            time.sleep(1)

@app.route('/')
def index():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Drone Video Stream</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: white; }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { text-align: center; color: #00ff88; }
            .video-container { text-align: center; margin: 20px 0; }
            .status { background: #333; padding: 15px; border-radius: 8px; margin: 20px 0; }
            .status h3 { margin-top: 0; color: #00ff88; }
            .info { background: #444; padding: 10px; border-radius: 5px; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚁 Drone Video Stream</h1>
            
            <div class="video-container">
                <img src="/video_feed" style="max-width: 100%; border: 2px solid #00ff88; border-radius: 8px;">
            </div>
            
            <div class="status">
                <h3>📡 Connection Status</h3>
                <div class="info">
                    <strong>WiFi Network:</strong> Drone_Network<br>
                    <strong>Password:</strong> drone123<br>
                    <strong>Drone IP:</strong> 192.168.4.1
                </div>
            </div>
            
            <div class="status">
                <h3>🔗 Stream URLs</h3>
                <div class="info">
                    <strong>RTSP Stream:</strong> rtsp://192.168.4.1:8554/stream<br>
                    <strong>Web Interface:</strong> http://192.168.4.1:8080<br>
                    <strong>VLC Player:</strong> Media → Open Network Stream → rtsp://192.168.4.1:8554/stream
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # Start camera thread
    threading.Thread(target=camera_thread, daemon=True).start()
    
    # Start web server
    print("Starting drone video web server...")
    print("Connect to WiFi: Drone_Network (password: drone123)")
    print("Web interface: http://192.168.4.1:8080")
    print("RTSP stream: rtsp://192.168.4.1:8554/stream")
    
    app.run(host='0.0.0.0', port=8080, debug=False)
```

### 8. **Make Scripts Executable**
```bash
chmod +x ~/start_video_stream.sh
chmod +x ~/video_web_server.py
```

## 💻 PC Side Setup

### 1. **Connect to Drone WiFi**
- Look for WiFi network: **"Drone_Network"**
- Password: **"drone123"**
- Your PC will get IP like: **192.168.4.2**

### 2. **Test Connection**
```bash
# Ping drone
ping 192.168.4.1

# Check if ports are open
telnet 192.168.4.1 8080
telnet 192.168.4.1 8554
```

### 3. **View Video Stream**

#### **Option A: Web Browser (Easiest)**
```
http://192.168.4.1:8080
```

#### **Option B: VLC Media Player**
1. Open VLC
2. Media → Open Network Stream
3. Enter: `rtsp://192.168.4.1:8554/stream`
4. Click Play

#### **Option C: FFmpeg**
```bash
# View stream
ffplay rtsp://192.168.4.1:8554/stream

# Record stream
ffmpeg -i rtsp://192.168.4.1:8554/stream -c copy drone_video.mp4
```

## 🔄 **Starting the System**

### **On Drone (Raspberry Pi 5):**
```bash
# Start video streaming
~/start_video_stream.sh

# Or start manually:
# Terminal 1: RTSP server
ffmpeg -f v4l2 -i /dev/video0 -c:v libx264 -preset ultrafast -tune zerolatency -f rtsp rtsp://0.0.0.0:8554/stream

# Terminal 2: Web server
python3 ~/video_web_server.py
```

### **On PC:**
1. Connect to "Drone_Network" WiFi
2. Open browser: `http://192.168.4.1:8080`
3. Or use VLC: `rtsp://192.168.4.1:8554/stream`

## 📊 **Performance Optimization**

### **For Better Quality:**
```bash
# Higher resolution
ffmpeg -f v4l2 -i /dev/video0 \
       -c:v libx264 -preset ultrafast \
       -tune zerolatency \
       -s 1280x720 \
       -b:v 2000k \
       -f rtsp rtsp://0.0.0.0:8554/stream
```

### **For Lower Latency:**
```bash
# Lower latency settings
ffmpeg -f v4l2 -i /dev/video0 \
       -c:v libx264 -preset ultrafast \
       -tune zerolatency \
       -profile:v baseline \
       -level 3.0 \
       -f rtsp rtsp://0.0.0.0:8554/stream
```

## 🚨 **Troubleshooting**

### **WiFi Connection Issues:**
```bash
# Check WiFi status on drone
iwconfig wlan0
ifconfig wlan0

# Restart WiFi services
sudo systemctl restart hostapd
sudo systemctl restart dnsmasq
```

### **Video Stream Issues:**
```bash
# Check camera on drone
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext

# Test camera manually
ffplay /dev/video0
```

### **Network Issues:**
```bash
# Check network on PC
ipconfig /all  # Windows
ifconfig       # Linux/Mac

# Test connectivity
ping 192.168.4.1
telnet 192.168.4.1 8080
```

## 📱 **Mobile Viewing**

You can also view the stream on mobile devices:

1. **Connect mobile to "Drone_Network" WiFi**
2. **Open browser: `http://192.168.4.1:8080`**
3. **Use VLC mobile app: `rtsp://192.168.4.1:8554/stream`**

## 🎯 **Next Steps**

Once wireless streaming is working:

1. **Test range** - walk around with your PC
2. **Optimize quality** - adjust resolution and bitrate
3. **Add recording** - enable video saving
4. **Multiple viewers** - multiple PCs can connect simultaneously
5. **Extend range** - add WiFi repeaters if needed

Your drone now streams video wirelessly to any device on the network! 🚁📹✨
