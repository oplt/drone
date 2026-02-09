from __future__ import print_function
from dronekit import connect, VehicleMode
from pymavlink import mavutil
import time

# --------------------------
# CONFIG
# --------------------------
CONNECTION_STRING = "/dev/ttyUSB0"   # or "udp:127.0.0.1:14550"
BAUD_RATE = 57600

TARGET_RISE = 0.3     # 30 cm
HOVER_TIME = 2        # seconds to hover at target alt
UP_VEL = -0.3         # m/s (negative in NED = up)
DOWN_VEL = 0.3        # m/s (positive in NED = down)
CMD_RATE_HZ = 10      # how often to send velocity commands
# --------------------------


def send_vertical_velocity(vehicle, vel_z, duration):
    """
    Send a vertical velocity command (body-NED frame) for `duration` seconds.
    vel_z < 0 => up, vel_z > 0 => down.
    """
    msg = vehicle.message_factory.set_position_target_local_ned_encode(
        0,                      # time_boot_ms (ignored)
        0, 0,                   # target system, target component
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        0b0000111111000111,     # type_mask: ignore pos, accel, yaw, yaw_rate; use velocity only
        0, 0, 0,                # x, y, z positions (ignored)
        0, 0, vel_z,            # vx, vy, vz in m/s
        0, 0, 0,                # ax, ay, az (ignored)
        0, 0                    # yaw, yaw_rate (ignored)
    )
    end_time = time.time() + duration
    period = 1.0 / CMD_RATE_HZ

    while time.time() < end_time:
        vehicle.send_mavlink(msg)
        vehicle.flush()
        time.sleep(period)


def main():
    print("Connecting to vehicle on %s ..." % CONNECTION_STRING)
    vehicle = connect(CONNECTION_STRING, baud=BAUD_RATE, wait_ready=True)
    print("Connected.\n")

    print("Current mode:", vehicle.mode.name)
    print("Setting mode GUIDED_NOGPS...")
    vehicle.mode = VehicleMode("GUIDED_NOGPS")
    while vehicle.mode.name != "GUIDED_NOGPS":
        print("  Waiting for GUIDED_NOGPS mode...")
        time.sleep(1)
    print("Mode is now:", vehicle.mode.name)

    # Wait until system is armable (baro, IMU, etc. OK)
    print("\nWaiting for vehicle to be armable...")
    while not vehicle.is_armable:
        print("  Not armable yet... (system_status=%s, ekf_ok=%s)" %
              (vehicle.system_status.state, vehicle.ekf_ok))
        time.sleep(1)
    print("Vehicle is armable.\n")

    # ARM
    print("Arming motors...")
    vehicle.armed = True
    while not vehicle.armed:
        print("  Waiting for arming...")
        time.sleep(1)
    print("Motors ARMED. They should be spinning at idle now.\n")

    input(">>> Press ENTER to rise ~30 cm <<<")

    # Take current baro-based relative altitude as reference
    start_alt = vehicle.location.global_relative_frame.alt or 0.0
