from __future__ import print_function
from dronekit import connect
from pymavlink import mavutil
import time

# Adjust if needed
# CONNECTION_STRING = "/dev/ttyACM0"
CONNECTION_STRING = "/dev/ttyUSB0"
BAUD_RATE = 57600

THROTTLE_TYPE = 0   # 0 = percentage, 1 = PWM
THROTTLE_PERCENT = 30  # 50% like your QGC test
DURATION = 3        # seconds per motor

def send_motor_test(vehicle, motor, throttle_percent, duration):
    print(f"Testing motor {motor} at {throttle_percent}% for {duration}s (DISARMED)...")

    msg = vehicle.message_factory.command_long_encode(
        1, 1,  # target system, component (1,1 is fine)
        mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST,
        0,     # confirmation
        motor,           # param1: motor number (1–4 for quad)
        THROTTLE_TYPE,   # param2: throttle type (0 = percentage)
        float(throttle_percent),  # param3: throttle (0–100)
        float(duration),          # param4: timeout (seconds)
        0, 0, 0        # param5–7: unused
    )
    vehicle.send_mavlink(msg)
    vehicle.flush()

def main():
    print(f"Connecting to {CONNECTION_STRING} ...")
    vehicle = connect(CONNECTION_STRING, baud=BAUD_RATE, wait_ready=False)
    print("Connected.\n")

    # Make sure we are DISARMED (QGC motor test is also disarmed)
    print("Ensuring vehicle is DISARMED for motor test...")
    vehicle.armed = False
    time.sleep(2)

    print("Starting motor tests (props OFF, LiPo connected)...\n")
    for m in range(1, 5):
        send_motor_test(vehicle, m, THROTTLE_PERCENT, DURATION)
        time.sleep(DURATION + 1)

    print("\nMotor tests complete.")
    vehicle.close()

if __name__ == "__main__":
    main()
