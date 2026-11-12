from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    default = str(Path(get_package_share_directory("rover_autonomy")) / "config/rover.yaml")
    config = {"config_path": LaunchConfiguration("config")}
    live = {"hardware_enabled": ParameterValue(LaunchConfiguration("hardware_enabled"), value_type=bool)}
    return LaunchDescription(
        [
            DeclareLaunchArgument("config", default_value=default),
            DeclareLaunchArgument("hardware_enabled", default_value="false"),
            DeclareLaunchArgument("camera_backend", default_value="picamera2"),
            DeclareLaunchArgument("start_camera", default_value="true"),
            Node(
                package="rover_autonomy",
                executable="camera_node",
                condition=IfCondition(LaunchConfiguration("start_camera")),
                parameters=[config, {"backend": LaunchConfiguration("camera_backend")}],
                output="screen",
            ),
            Node(
                package="rover_autonomy", executable="perception_node", parameters=[config], output="screen"
            ),
            Node(
                package="rover_autonomy",
                executable="supervisor_node",
                parameters=[config, live],
                output="screen",
            ),
            Node(
                package="rover_autonomy", executable="base_node", parameters=[config, live], output="screen"
            ),
        ]
    )
