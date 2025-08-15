#!/usr/bin/env python3
"""
Test script for drone video streaming functionality
Run this to verify your camera setup before running the full drone application
"""

import cv2
import time
import os
from video.stream import DroneVideoStream
from config import settings

def test_basic_camera():
    """Test basic camera access with OpenCV"""
    print("🔍 Testing basic camera access...")
    
    # Try to open camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Failed to open camera with index 0")
        return False
    
    # Try to read a frame
    ret, frame = cap.read()
    if not ret:
        print("❌ Failed to read frame from camera")
        cap.release()
        return False
    
    print(f"✅ Camera working! Frame size: {frame.shape}")
    cap.release()
    return True

def test_drone_video_stream():
    """Test the enhanced drone video stream"""
    print("\n🚁 Testing drone video stream...")
    
    try:
        # Create video stream with minimal settings
        video = DroneVideoStream(
            source=0,
            width=640,
            height=480,
            fps=30,
            open_timeout_s=5.0,
            enable_recording=False  # Disable recording for testing
        )
        
        print("✅ DroneVideoStream created successfully")
        
        # Test frame generation
        frame_count = 0
        start_time = time.time()
        
        print("📹 Capturing frames (press Ctrl+C to stop)...")
        
        for _, frame in video.frames():
            frame_count += 1
            
            # Display frame count every 30 frames
            if frame_count % 30 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed
                print(f"   Frames: {frame_count}, FPS: {fps:.1f}")
            
            # Limit test to 100 frames
            if frame_count >= 100:
                break
        
        elapsed = time.time() - start_time
        avg_fps = frame_count / elapsed
        print(f"✅ Test completed! Captured {frame_count} frames in {elapsed:.1f}s (avg FPS: {avg_fps:.1f})")
        
        video.close()
        return True
        
    except Exception as e:
        print(f"❌ Error testing drone video stream: {e}")
        return False

def test_camera_devices():
    """Check available camera devices"""
    print("\n📷 Checking available camera devices...")
    
    # Check /dev/video* devices
    video_devices = []
    for i in range(10):  # Check up to /dev/video9
        if os.path.exists(f"/dev/video{i}"):
            video_devices.append(i)
    
    if video_devices:
        print(f"✅ Found video devices: {video_devices}")
        for device in video_devices:
            print(f"   /dev/video{device}")
    else:
        print("❌ No video devices found")
    
    return video_devices

def test_configuration():
    """Display current video configuration"""
    print("\n⚙️  Current video configuration:")
    print(f"   DRONE_VIDEO_ENABLED: {settings.drone_video_enabled}")
    print(f"   DRONE_VIDEO_SOURCE: {settings.drone_video_source}")
    print(f"   DRONE_VIDEO_WIDTH: {settings.drone_video_width}")
    print(f"   DRONE_VIDEO_HEIGHT: {settings.drone_video_height}")
    print(f"   DRONE_VIDEO_FPS: {settings.drone_video_fps}")
    print(f"   DRONE_VIDEO_TIMEOUT: {settings.drone_video_timeout}")
    print(f"   DRONE_VIDEO_SAVE_STREAM: {settings.drone_video_save_stream}")
    print(f"   DRONE_VIDEO_SAVE_PATH: {settings.drone_video_save_path}")

def main():
    """Main test function"""
    print("🚁 Drone Video Streaming Test")
    print("=" * 40)
    
    # Test configuration
    test_configuration()
    
    # Check camera devices
    devices = test_camera_devices()
    
    if not devices:
        print("\n❌ No camera devices found. Please check your camera connection.")
        return
    
    # Test basic camera
    if not test_basic_camera():
        print("\n❌ Basic camera test failed. Please check camera permissions and drivers.")
        return
    
    # Test drone video stream
    if test_drone_video_stream():
        print("\n🎉 All tests passed! Your drone video setup is working correctly.")
        print("\nYou can now run the main drone application with video streaming enabled.")
    else:
        print("\n❌ Drone video stream test failed. Check the error messages above.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
