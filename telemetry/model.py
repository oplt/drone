from pymavlink import mavutil
from config import settings

conn = mavutil.mavlink_connection(settings.drone_conn, baud=57600)

conn.mav.heartbeat_send(
    mavutil.mavlink.MAV_TYPE_GCS,
    mavutil.mavlink.MAV_AUTOPILOT_INVALID,
    0,
    0,
    mavutil.mavlink.MAV_STATE_ACTIVE,
)

conn.wait_heartbeat()
print("Connected to vehicle")

# Request streams
conn.mav.request_data_stream_send(
    conn.target_system, conn.target_component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1
)

while True:
    msg = conn.recv_match(blocking=True)

    if msg:
        print(msg.to_dict())
    else:
        print("No data")
