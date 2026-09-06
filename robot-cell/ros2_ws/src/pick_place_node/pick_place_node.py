"""
pick_place_node.py
--------------------
ROS2 node that drives the UR10 pick-and-place cycle for the Smart Factory
Digital Twin. Uses the MoveIt Python API (moveit_py) for motion planning
and execution, and reacts to vision inspection results published by
inspection_node.py (bridged from MQTT -> ROS2, or subscribed directly if
running the bridge as a ROS2 topic republisher).

Cycle logic:
  1. Wait for /factory/robot/cell_ready to go TRUE (from PLC/Ignition).
  2. Move to a "home/observe" pose above the pick station.
  3. Wait for a vision inspection result on /factory/vision/inspection_result.
  4. If "pass": plan + execute pick at conveyor_pick_point, place at the
     downstream assembly fixture pose.
  5. If "fail_misaligned" or "fail_defect": plan + execute pick at
     conveyor_pick_point, place at reject_bin_point.
  6. Return to home pose and signal cycle complete back to the PLC.

Run standalone for testing the state machine without real MoveIt hardware
by passing --dry-run, which logs planned moves instead of executing them.
"""

import argparse
import json
import time
from enum import Enum, auto

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String, Bool
from geometry_msgs.msg import PoseStamped

try:
    from moveit.planning import MoveItPy
    from moveit.core.robot_state import RobotState
    MOVEIT_AVAILABLE = True
except ImportError:
    MOVEIT_AVAILABLE = False


class CycleState(Enum):
    WAIT_CELL_READY = auto()
    MOVE_HOME = auto()
    WAIT_VISION_RESULT = auto()
    PICK = auto()
    PLACE_ASSEMBLY = auto()
    PLACE_REJECT = auto()
    RETURN_HOME = auto()
    CYCLE_COMPLETE = auto()


# Named poses (meters, quaternion). Replace with values calibrated against
# the actual assembly_station.world frames (conveyor_pick_point, etc.).
POSES = {
    "home": {"position": [0.0, 0.0, 0.6], "orientation": [0.0, 0.0, 0.0, 1.0]},
    "conveyor_pick_point": {"position": [1.2, 0.0, 0.55], "orientation": [0.0, 1.0, 0.0, 0.0]},
    "assembly_fixture_point": {"position": [0.6, 0.6, 0.55], "orientation": [0.0, 1.0, 0.0, 0.0]},
    "reject_bin_point": {"position": [1.2, -0.8, 0.45], "orientation": [0.0, 1.0, 0.0, 0.0]},
}

PLANNING_GROUP = "ur10_arm"
GRIPPER_GROUP = "ur10_gripper"


class PickPlaceNode(Node):
    def __init__(self, dry_run: bool = False):
        super().__init__("pick_place_node")

        self.declare_parameter("vision_topic", "/factory/vision/inspection_result")
        self.declare_parameter("cell_ready_topic", "/factory/robot/cell_ready")
        self.declare_parameter("pick_pose_frame", "conveyor_pick_point")
        self.declare_parameter("place_pose_frame", "reject_bin_point")

        self.vision_topic = self.get_parameter("vision_topic").value
        self.cell_ready_topic = self.get_parameter("cell_ready_topic").value

        self.dry_run = dry_run or not MOVEIT_AVAILABLE
        if not MOVEIT_AVAILABLE:
            self.get_logger().warn("moveit_py not found - running in dry-run/log-only mode")

        self.state = CycleState.WAIT_CELL_READY
        self.cell_ready = False
        self.latest_vision_result = None
        self.cycles_completed = 0
        self.parts_rejected = 0

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

        self.cell_ready_sub = self.create_subscription(
            Bool, self.cell_ready_topic, self._on_cell_ready, qos
        )
        self.vision_sub = self.create_subscription(
            String, self.vision_topic, self._on_vision_result, qos
        )
        self.cycle_status_pub = self.create_publisher(String, "/factory/robot/cycle_status", qos)
        self.cycle_active_pub = self.create_publisher(Bool, "/factory/robot/cycle_active", qos)

        if not self.dry_run:
            self.moveit = MoveItPy(node_name="pick_place_moveit_py")
            self.arm = self.moveit.get_planning_component(PLANNING_GROUP)
            self.gripper = self.moveit.get_planning_component(GRIPPER_GROUP)
        else:
            self.moveit = None

        self.timer = self.create_timer(0.5, self._run_state_machine)
        self.get_logger().info(f"pick_place_node started (dry_run={self.dry_run})")

    def _on_cell_ready(self, msg: Bool):
        self.cell_ready = msg.data

    def _on_vision_result(self, msg: String):
        try:
            payload = json.loads(msg.data)
            self.latest_vision_result = payload.get("status")
        except json.JSONDecodeError:
            self.latest_vision_result = msg.data
        self.get_logger().info(f"Received vision result: {self.latest_vision_result}")

    def _publish_status(self, text: str, active: bool):
        self.cycle_status_pub.publish(String(data=text))
        self.cycle_active_pub.publish(Bool(data=active))

    def _move_to_pose(self, pose_name: str) -> bool:
        pose_cfg = POSES[pose_name]
        self.get_logger().info(f"Planning move to '{pose_name}': {pose_cfg}")

        if self.dry_run:
            time.sleep(0.5)
            self.get_logger().info(f"[DRY RUN] Executed move to {pose_name}")
            return True

        target = PoseStamped()
        target.header.frame_id = "base_link"
        target.pose.position.x, target.pose.position.y, target.pose.position.z = pose_cfg["position"]
        (target.pose.orientation.x, target.pose.orientation.y,
         target.pose.orientation.z, target.pose.orientation.w) = pose_cfg["orientation"]

        self.arm.set_start_state_to_current_state()
        self.arm.set_goal_state(pose_stamped_msg=target, pose_link="tool0")
        plan_result = self.arm.plan()

        if plan_result:
            self.moveit.execute(plan_result.trajectory, controllers=[])
            return True

        self.get_logger().error(f"Motion planning failed for pose '{pose_name}'")
        return False

    def _actuate_gripper(self, close: bool) -> bool:
        action = "close" if close else "open"
        self.get_logger().info(f"Gripper action: {action}")
        if self.dry_run:
            time.sleep(0.2)
            return True

        self.gripper.set_start_state_to_current_state()
        self.gripper.set_goal_state(configuration_name=("closed" if close else "open"))
        plan_result = self.gripper.plan()
        if plan_result:
            self.moveit.execute(plan_result.trajectory, controllers=[])
            return True
        return False

    def _run_state_machine(self):
        if self.state == CycleState.WAIT_CELL_READY:
            if self.cell_ready:
                self._publish_status("cell_ready_confirmed", False)
                self.state = CycleState.MOVE_HOME

        elif self.state == CycleState.MOVE_HOME:
            if self._move_to_pose("home"):
                self.latest_vision_result = None
                self.state = CycleState.WAIT_VISION_RESULT
                self._publish_status("waiting_for_vision", False)

        elif self.state == CycleState.WAIT_VISION_RESULT:
            if self.latest_vision_result is not None:
                self._publish_status("cycle_started", True)
                self.state = CycleState.PICK

        elif self.state == CycleState.PICK:
            if self._move_to_pose("conveyor_pick_point") and self._actuate_gripper(close=True):
                if self.latest_vision_result == "pass":
                    self.state = CycleState.PLACE_ASSEMBLY
                elif self.latest_vision_result in ("fail_misaligned", "fail_defect"):
                    self.state = CycleState.PLACE_REJECT
                else:
                    self.get_logger().warn(f"Unexpected vision result '{self.latest_vision_result}', aborting cycle")
                    self.state = CycleState.RETURN_HOME

        elif self.state == CycleState.PLACE_ASSEMBLY:
            if self._move_to_pose("assembly_fixture_point") and self._actuate_gripper(close=False):
                self.cycles_completed += 1
                self.state = CycleState.RETURN_HOME

        elif self.state == CycleState.PLACE_REJECT:
            if self._move_to_pose("reject_bin_point") and self._actuate_gripper(close=False):
                self.cycles_completed += 1
                self.parts_rejected += 1
                self.state = CycleState.RETURN_HOME

        elif self.state == CycleState.RETURN_HOME:
            if self._move_to_pose("home"):
                self.state = CycleState.CYCLE_COMPLETE

        elif self.state == CycleState.CYCLE_COMPLETE:
            self._publish_status(
                json.dumps({"cycles_completed": self.cycles_completed, "parts_rejected": self.parts_rejected}),
                False,
            )
            self.get_logger().info(
                f"Cycle complete. Total: {self.cycles_completed}, Rejected: {self.parts_rejected}"
            )
            self.state = CycleState.WAIT_VISION_RESULT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Log planned moves without executing on MoveIt")
    args, _ = parser.parse_known_args()

    rclpy.init()
    node = PickPlaceNode(dry_run=args.dry_run)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
