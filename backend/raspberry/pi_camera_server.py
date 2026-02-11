from flask import Flask, Response
from picamera2 import Picamera2
import cv2

app = Flask(__name__)

# Initialize camera
picam2 = Picamera2()
video_config = picam2.create_video_configuration(main={"size": (1280, 720)})
picam2.configure(video_config)
picam2.start()


def generate_frames():
    while True:
        # Capture a frame as a numpy array (BGR)
        frame = picam2.capture_array()

        # Encode as JPEG
        ret, buffer = cv2.imencode(".jpg", frame)
        if not ret:
            continue

        jpg_bytes = buffer.tobytes()

        # MJPEG stream format
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg_bytes + b"\r\n")


@app.route("/video_feed")
def video_feed():
    # Browser/clients can read this as a MJPEG stream
    return Response(
        generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/")
def index():
    return (
        "<html><body>"
        "<h1>Raspberry Pi Camera Stream</h1>"
        "<img src='/video_feed' />"
        "</body></html>"
    )


if __name__ == "__main__":
    # host='0.0.0.0' makes it accessible from other devices in the same network
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
