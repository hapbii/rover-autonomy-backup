# Source this file from any terminal on the Pi.
_ROVER_WS="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source /opt/ros/jazzy/setup.bash
[ ! -f "$_ROVER_WS/.venv/bin/activate" ] || source "$_ROVER_WS/.venv/bin/activate"
[ ! -f "$_ROVER_WS/install/setup.bash" ] || source "$_ROVER_WS/install/setup.bash"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-9}"
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
unset _ROVER_WS
