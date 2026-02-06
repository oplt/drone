from __future__ import print_function
from dronekit import connect, VehicleMode
import time

# -------------------------
# CONFIG
# -------------------------
CONNECTION_STRING = "/dev/ttyUSB0"   # or "udp:127.0.0.1:14550"
BAUD_RATE = 57600
ARM_TIME = 2  # seconds motors will spin at idle
# -------------------------

def main():
    print("Connecting to vehicle...")
    vehicle = connect(CONNECTION_STRING, baud=BAUD_RATE, wait_ready=False)
    print("Connected.\n")

    # Make sure system is armable (IMU, baro, etc.)
    print("Waiting for vehicle to be armable...")
    # while not vehicle.is_armable:
    #     print("  Not armable yet...")
    #     time.sleep(1)
    # print("Vehicle is armable.\n")

    # Set mode to GUIDED or STABILIZE — either works for arming motors
    print("Setting mode to GUIDED_NOGPS...")
    vehicle.mode = VehicleMode("GUIDED_NOGPS")
    while vehicle.mode.name != "GUIDED_NOGPS":
        print("  Waiting for GUIDED_NOGPS mode...")
        time.sleep(1)
    print("Mode set.\n")

    # ARM
    print("Arming motors...")
    vehicle.armed = True
    while not vehicle.armed:
        print("  Waiting for arming...")
        time.sleep(1)
    print("Motors ARMED — spinning at idle.\n")

    # Let motors run for ARM_TIME
    print(f"Spinning motors for {ARM_TIME} seconds...")
    time.sleep(ARM_TIME)

    # DISARM
    print("Disarming motors...")
    vehicle.armed = False
    while vehicle.armed:
        print("  Waiting for disarming...")
        time.sleep(1)
    print("Motors DISARMED.\n")

    print("Done.")
    vehicle.close()

if __name__ == "__main__":
    main()
