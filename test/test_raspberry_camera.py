# debug_pi_camera.py
import paramiko
import time
import logging
from config import settings

logging.basicConfig(level=logging.DEBUG)

def test_pi_camera():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname="192.168.129.14",
            username="pi",
            key_filename= settings.ssh_key_path,
            timeout=10
        )

        # Check Python version
        stdin, stdout, stderr = ssh.exec_command("python3 --version")
        print(f"Python: {stdout.read().decode().strip()}")

        # Check packages
        stdin, stdout, stderr = ssh.exec_command("python3 -c 'import flask; print(\"Flask OK\"); import cv2; print(\"OpenCV OK\"); from picamera2 import Picamera2; print(\"Picamera2 OK\")'")
        print("Package check:", stderr.read().decode())

        # Check if script exists
        stdin, stdout, stderr = ssh.exec_command("ls -la /home/polat/drone_cam/")
        print(f"Directory listing:\n{stdout.read().decode()}")

        # Try running the script manually
        print("\nTrying to run camera server...")
        stdin, stdout, stderr = ssh.exec_command("cd /home/polat/drone_cam && python3 pi_camera_server.py 2>&1 & sleep 3 && ps aux | grep pi_camera")
        print(f"Output:\n{stdout.read().decode()}")
        print(f"Errors:\n{stderr.read().decode()}")

        # Check logs
        print("\nChecking logs...")
        stdin, stdout, stderr = ssh.exec_command("cat /tmp/drone_camera.log 2>/dev/null || echo 'No logs yet'")
        print(f"Logs:\n{stdout.read().decode()}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    test_pi_camera()