from dronekit import connect, VehicleMode, LocationGlobalRelative
import math
import time

# Connect to SITL (adjust if needed)
vehicle = connect('tcp:127.0.0.1:5762', wait_ready=True)

def arm_and_takeoff(aTargetAltitude):
    while not vehicle.is_armable:
        time.sleep(1)
    vehicle.mode = VehicleMode("GUIDED")
    vehicle.armed = True
    while not vehicle.armed:
        time.sleep(1)
    vehicle.simple_takeoff(aTargetAltitude)
    while True:
        alt = vehicle.location.global_relative_frame.alt
        if alt >= aTargetAltitude * 0.95:
            break
        time.sleep(1)

def get_location_metres(original_location, dNorth, dEast):
    earth_radius = 6378137.0  # meters
    dLat = dNorth / earth_radius
    dLon = dEast / (earth_radius * math.cos(math.pi * original_location.lat / 180))
    newlat = original_location.lat + (dLat * 180 / math.pi)
    newlon = original_location.lon + (dLon * 180 / math.pi)
    return LocationGlobalRelative(newlat, newlon, original_location.alt)

# Take off to 10 meters
arm_and_takeoff(10)

print("Flying 50 m right (east)...")
current_location = vehicle.location.global_relative_frame
target_location = get_location_metres(current_location, 0, 50)  # North=0, East=50
vehicle.simple_goto(target_location)

# Wait until close to target
time.sleep(20)

print("Landing...")
vehicle.mode = VehicleMode("LAND")
vehicle.close()
