from __future__ import print_function
from dronekit import connect
import dronekit
import time

CONNECTION_STRING = "/dev/ttyUSB0"
BAUD_RATE=57600

def main():
    print(f"Connecting to vehicle on: {CONNECTION_STRING}")

    vehicle = connect(CONNECTION_STRING, baud=BAUD_RATE, wait_ready=False, heartbeat_timeout=60)
    print("Connected (link OK over UDP).")

    try:
        print("Waiting for basic attributes (mode, GPS, battery)...")
        vehicle.wait_ready(
            'system_status', 'mode', 'gps_0', 'battery',
            timeout=60
        )
    except dronekit.TimeoutError as e:
        print("WARNING: wait_ready timed out:", e)
        print("Continuing with whatever data is available...")

    print("\n=== VEHICLE INFO ===")
    print(" Autopilot firmware version:", getattr(vehicle, "version", "n/a"))
    print(" System status:", getattr(vehicle, "system_status", "n/a"))
    print(" Mode:", getattr(vehicle, "mode", "n/a"))
    print(" GPS:", getattr(vehicle, "gps_0", "n/a"))
    print(" Battery:", getattr(vehicle, "battery", "n/a"))
    print(" EKF OK?:", getattr(vehicle, "ekf_ok", "n/a"))
    print("====================\n")

    print("Reading telemetry for 10 seconds...\n")
    for i in range(10):
        alt = getattr(
            getattr(getattr(vehicle, "location", None), "global_relative_frame", None),
            "alt",
            None
        )
        mode_name = getattr(getattr(vehicle, "mode", None), "name", "n/a")

        print(
            f"t={i+1:2d}s | "
            f"Mode: {mode_name:>8} | "
            f"GPS: {getattr(vehicle, 'gps_0', 'n/a')} | "
            f"Alt: {alt} m | "
            f"Battery: {getattr(vehicle, 'battery', 'n/a')}"
        )
        time.sleep(1)

    print("\nClosing vehicle connection.")
    vehicle.close()
    print("Done.")

if __name__ == "__main__":
    main()
