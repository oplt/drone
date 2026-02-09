from dronekit import connect
from pymavlink import mavutil
import time

CONN = "/dev/ttyUSB0"   # or /dev/ttyACM0 as needed
# CONN = "/dev/ttyACM0"

BAUD = 57600

def status_text_listener(self, name, message):
    # ArduPilot sends PREARM, ARMING, etc. as STATUSTEXT
    print(f"[STATUSTEXT] severity={message.severity} text={message.text}")

vehicle = connect(CONN, baud=BAUD, wait_ready=False)
vehicle.add_message_listener('STATUSTEXT', status_text_listener)

print("Listening for 20s… move the board, try to arm from your TX or GCS if you want.")
time.sleep(20)

vehicle.close()
