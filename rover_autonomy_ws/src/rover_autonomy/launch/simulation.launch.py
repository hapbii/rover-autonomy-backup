from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    default = str(Path(get_package_share_directory("rover_autonomy")) / "config/rover.yaml")
    parameters = {"config_path": LaunchConfiguration("config"), "hardware_enabled": False}
    return LaunchDescription(
        [
            DeclareLaunchArgument("config", default_value=default),
            DeclareLaunchArgument("obstacle", default_value="false"),
            Node(
                package="rover_autonomy",
                executable="simulation_node",
                parameters=[{"obstacle": ParameterValue(LaunchConfiguration("obstacle"), value_type=bool)}],
                output="screen",
            ),
            Node(
                package="rover_autonomy",
                executable="supervisor_node",
                parameters=[parameters],
                output="screen",
            ),
            Node(package="rover_autonomy", executable="base_node", parameters=[parameters], output="screen"),
        ]
    )
