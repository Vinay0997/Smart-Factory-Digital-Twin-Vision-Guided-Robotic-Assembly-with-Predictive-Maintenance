"""
factory_cell.launch.py
------------------------
ROS2 launch file for the Smart Factory Digital Twin robot cell.

Brings up:
  1. Gazebo simulation loaded with the assembly_station.world (conveyor +
     pick station + UR10-class arm).
  2. Robot state publisher from the UR10 URDF/xacro description.
  3. ros2_control controller manager + trajectory controllers.
  4. MoveIt move_group node for motion planning.
  5. The pick_place_node that runs the pick-and-place cycle and talks to
     the PLC/vision layer over ROS2 topics bridged to MQTT.

Usage:
    ros2 launch robot-cell/ros2_ws/launch/factory_cell.launch.py
    ros2 launch factory_cell.launch.py use_sim_time:=true world:=assembly_station.world
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    world_file = LaunchConfiguration("world")
    robot_description_pkg = "ur10_description"
    moveit_config_pkg = "ur10_moveit_config"

    declare_use_sim_time = DeclareLaunchArgument(
        "use_sim_time", default_value="true", description="Use simulation clock from Gazebo"
    )
    declare_world = DeclareLaunchArgument(
        "world", default_value="assembly_station.world", description="Gazebo world file to load"
    )

    # --- 1. Launch Gazebo with the assembly station world ---
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory("ros_gz_sim"), "launch", "gz_sim.launch.py")
        ),
        launch_arguments={
            "gz_args": PathJoinSubstitution(
                [FindPackageShare("robot_cell"), "gazebo_worlds", world_file]
            )
        }.items(),
    )

    # --- 2. Robot state publisher (URDF/xacro -> TF tree) ---
    robot_description_content = PathJoinSubstitution(
        [FindPackageShare(robot_description_pkg), "urdf", "ur10.urdf.xacro"]
    )
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="screen",
        parameters=[
            {"use_sim_time": use_sim_time},
            {"robot_description": robot_description_content},
        ],
    )

    # --- 3. Spawn the robot into Gazebo ---
    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        arguments=["-topic", "robot_description", "-name", "ur10_pick_place", "-z", "0.05"],
        output="screen",
    )

    # --- 4. ros_gz_bridge: bridge camera + clock topics between Gazebo and ROS2 ---
    ros_gz_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        name="ros_gz_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            "/camera/image_raw@sensor_msgs/msg/Image[gz.msgs.Image",
            "/camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo",
        ],
        output="screen",
    )

    # --- 5. Controller manager + trajectory controllers (ros2_control) ---
    controller_manager_spawner_jsb = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster"],
        output="screen",
    )
    controller_manager_spawner_arm = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["ur10_arm_controller"],
        output="screen",
    )

    # --- 6. MoveIt move_group for motion planning ---
    move_group = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [FindPackageShare(moveit_config_pkg), "launch", "move_group.launch.py"]
            )
        ),
        launch_arguments={"use_sim_time": use_sim_time}.items(),
    )

    # --- 7. Pick-and-place application node (delayed start until controllers are up) ---
    pick_place_node = TimerAction(
        period=8.0,
        actions=[
            Node(
                package="pick_place_node",
                executable="pick_place_node",
                name="pick_place_node",
                output="screen",
                parameters=[
                    {"use_sim_time": use_sim_time},
                    {"vision_topic": "/factory/vision/inspection_result"},
                    {"cell_ready_topic": "/factory/robot/cell_ready"},
                    {"pick_pose_frame": "conveyor_pick_point"},
                    {"place_pose_frame": "reject_bin_point"},
                ],
            )
        ],
    )

    return LaunchDescription(
        [
            declare_use_sim_time,
            declare_world,
            gazebo,
            robot_state_publisher,
            spawn_robot,
            ros_gz_bridge,
            controller_manager_spawner_jsb,
            controller_manager_spawner_arm,
            move_group,
            pick_place_node,
        ]
    )
