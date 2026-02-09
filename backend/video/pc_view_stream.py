import time
import requests
import paramiko
import cv2
import numpy as np
from backend.config import settings

# ---------- CONFIGURATION ----------
PI_HOST = settings.rasperry_ip
PI_USER = settings.rasperry_user
SSH_KEY_PATH = settings.ssh_key_path
REMOTE_PY_SCRIPT = settings.rasperry_streaming_script_path
PI_PORT = 5000
STREAM_URL = f"http://{PI_HOST}:{PI_PORT}/video_feed"

# ---------- SSH PART: START SERVER ON PI ----------

def start_streaming_server_via_ssh():
    """
    Connect to the Raspberry Pi via SSH and start the camera server in the background.
    Assumes passwordless login via SSH key already works.
    """

    # Command that starts the server and keeps it running after SSH returns
    command = (
        f"nohup python3 {REMOTE_PY_SCRIPT} "
        "> /tmp/pi_cam_server.log 2>&1 &"
    )

    print(f"[INFO] Connecting to {PI_HOST} via SSH as {PI_USER}...")
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(
        hostname=PI_HOST,
        username=PI_USER,
        key_filename=SSH_KEY_PATH,
        timeout=10,
    )

    print(f"[INFO] Running remote command: {command}")
    ssh.exec_command(command)
    ssh.close()
    print("[INFO] Remote server started (requested).")


def wait_for_stream(url, timeout=30):
    """
    Poll the stream URL until it responds with HTTP 200 or until timeout (seconds).
    """
    print(f"[INFO] Waiting for stream at {url} ...")
    start = time.time()

    while time.time() - start < timeout:
        try:
            r = requests.get(url, stream=True, timeout=3)
            if r.status_code == 200:
                print("[INFO] Stream is up!")
                r.close()
                return True
        except requests.RequestException:
            pass

        print("[INFO] Stream not ready yet, retrying...")
        time.sleep(2)

    print("[ERROR] Stream did not become ready within timeout.")
    return False


# ---------- MJPEG CLIENT PART (similar to your original) ----------

def mjpeg_stream(url):
    """
    Generator that yields individual JPEG frames from an MJPEG HTTP stream.
    """
    stream = requests.get(url, stream=True)
    bytes_buf = b""

    for chunk in stream.iter_content(chunk_size=1024):
        if not chunk:
            continue
        bytes_buf += chunk

        a = bytes_buf.find(b'\xff\xd8')  # JPEG start
        b = bytes_buf.find(b'\xff\xd9')  # JPEG end
        if a != -1 and b != -1 and b > a:
            jpg = bytes_buf[a:b+2]
            bytes_buf = bytes_buf[b+2:]

            img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                yield img


if __name__ == "__main__":
    # 1) Start the server on the Raspberry Pi via SSH
    start_streaming_server_via_ssh()

    # 2) Wait until the stream is reachable
    if not wait_for_stream(STREAM_URL, timeout=40):
        exit(1)

    # 3) Show frames in a window
    print("[INFO] Opening video window. Press 'q' to quit.")
    try:
        for frame in mjpeg_stream(STREAM_URL):
            cv2.imshow("Raspberry Pi Camera", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cv2.destroyAllWindows()
        print("[INFO] Video window closed.")
