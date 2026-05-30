# Warehouse ROS 2 Deployment

Backend and Jetson deploy separately.

Backend:
- run FastAPI plus Celery workers from existing `docker-compose.yml`.
- start a dedicated Celery worker for queue `warehouse-mapping`.
- set `WAREHOUSE_ROS_BRIDGE_URL=http://JETSON_HOST:8088`.
- frontend only talks to backend; object storage serves signed map assets.

Jetson:
- deploy `jetson_ros2_ws` on the companion computer.
- run `deploy/warehouse/jetson/docker-compose.jetson.yml` or the systemd unit.
- services expose:
  - HTTP bridge on `8088`
  - ROS graph/camera/Isaac launch through `warehouse_mapping_bridge`
  - MAVLink vision bridge
  - artifact exporter writing capture bundles under `/data/warehouse_ros`

Health:
- backend `/warehouse/perception/health` checks Jetson reachability.
- mission websocket includes `warehouse_mapping` health.
- alert on ROS bridge down, disk low, VSLAM loss, map export failure.

