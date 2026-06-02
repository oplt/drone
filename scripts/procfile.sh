#!/usr/bin/env bash
set -Eeuo pipefail

export ROS_DISTRO="${ROS_DISTRO:-jazzy}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_WS_SETUP="${ROS_WS_SETUP:-warehouse_ros2_ws/install/setup.bash}"

# Important when Honcho is launched from .venv:
# allow ROS Python tools to see apt-installed packages like tornado/argcomplete.
export PYTHONPATH="/usr/lib/python3/dist-packages:${PYTHONPATH:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATH="${PATH//$REPO_ROOT\/.venv\/bin:/}"
PATH="${PATH//:$REPO_ROOT\/.venv\/bin/}"
PATH="${PATH//$REPO_ROOT\/.venv\/bin/}"
PATH="${PATH//$REPO_ROOT\/backend\/.venv\/bin:/}"
PATH="${PATH//:$REPO_ROOT\/backend\/.venv\/bin/}"
PATH="${PATH//$REPO_ROOT\/backend\/.venv\/bin/}"
export PATH

source_ros_env() {
  local nounset_was_enabled=0

  case "$-" in
    *u*)
      nounset_was_enabled=1
      set +u
      ;;
  esac

  source "/opt/ros/${ROS_DISTRO}/setup.bash"

  if [ -f "${ROS_WS_SETUP}" ]; then
    source "${ROS_WS_SETUP}"
  else
    echo "[procfile.sh] WARNING: ROS_WS_SETUP not found: ${ROS_WS_SETUP}" >&2
  fi

  if [ "${nounset_was_enabled}" -eq 1 ]; then
    set -u
  fi
}

source_ros_env

echo "[procfile.sh] ROS_DISTRO=${ROS_DISTRO} ROS_DOMAIN_ID=${ROS_DOMAIN_ID}"
echo "[procfile.sh] ROS_WS_SETUP=${ROS_WS_SETUP}"
echo "[procfile.sh] PYTHONPATH=${PYTHONPATH}"
echo "[procfile.sh] exec: $*"

exec "$@"
