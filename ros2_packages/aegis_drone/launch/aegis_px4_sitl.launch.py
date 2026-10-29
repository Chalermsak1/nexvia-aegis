import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory("aegis_drone") if "aegis_drone" in os.environ.get("AMENT_PREFIX_PATH", "") else "."
    default_config_path = os.path.join(pkg_share, "config", "aegis_params.yaml")

    config_arg = DeclareLaunchArgument(
        "config_file",
        default_value=default_config_path,
        description="Path to AEGIS YAML parameter configuration file",
    )

    aegis_node = Node(
        package="aegis_drone",
        executable="aegis_drone_node",
        name="aegis_drone_node",
        output="screen",
        parameters=[LaunchConfiguration("config_file")],
        remappings=[
            ("/mavros/local_position/pose", "/mavros/local_position/pose"),
            ("/mavros/setpoint_raw/attitude", "/mavros/setpoint_raw/attitude"),
        ],
    )

    return LaunchDescription([
        config_arg,
        aegis_node,
    ])
