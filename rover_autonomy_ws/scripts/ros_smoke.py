"""Pi-only ROS integration smoke. Isolated domain, dry-run base, virtual range."""

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import rclpy
import yaml
from geometry_msgs.msg import TwistStamped
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Range
from std_msgs.msg import String
from std_srvs.srv import SetBool

ROOT = Path(__file__).resolve().parents[1]


class Probe(Node):
    def __init__(self, image):
        super().__init__("rover_integration_probe")
        self.state = {}
        self.vision = {}
        self.ranges = 0
        self.commands = 0
        self.command = (0.0, 0.0)
        self.max_linear = 0.0
        self.max_angular = 0.0
        self.reasons = set()
        self.mode = self.create_publisher(String, "/rover/mode", 1)
        self.arm = self.create_client(SetBool, "/rover/arm")
        self.emergency = self.create_client(SetBool, "/rover/emergency_stop")
        self.create_subscription(String, "/rover/state", self.on_state, 1)
        self.create_subscription(String, "/rover/vision", self.on_vision, qos_profile_sensor_data)
        self.create_subscription(Range, "/rover/range", self.on_range, qos_profile_sensor_data)
        self.create_subscription(TwistStamped, "/rover/cmd_vel", self.on_command, 1)
        if image:
            self.range_pub = self.create_publisher(Range, "/rover/range", qos_profile_sensor_data)
            self.create_timer(0.1, self.publish_virtual_range)

    def publish_virtual_range(self):
        message = Range()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "virtual_smoke_range"
        message.radiation_type = Range.ULTRASOUND
        message.field_of_view = 0.26
        message.min_range, message.max_range, message.range = 0.02, 4.0, 2.0
        self.range_pub.publish(message)

    def on_state(self, message):
        self.state = json.loads(message.data)
        self.reasons.add(self.state.get("reason", ""))

    def on_vision(self, message):
        self.vision = json.loads(message.data)

    def on_range(self, _):
        self.ranges += 1

    def on_command(self, message):
        self.commands += 1
        self.command = (message.twist.linear.x, message.twist.angular.z)
        self.max_linear = max(self.max_linear, abs(self.command[0]))
        self.max_angular = max(self.max_angular, abs(self.command[1]))

    def wait(self, condition, seconds=12):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            if condition():
                return
        raise TimeoutError(f"ROS smoke timed out; state={self.state}, commands={self.commands}")

    def call(self, client, value):
        if not client.wait_for_service(timeout_sec=5):
            raise TimeoutError("ROS service did not become available")
        future = client.call_async(SetBool.Request(data=value))
        self.wait(future.done, 5)
        result = future.result()
        if not result.success:
            raise AssertionError(result.message)


def stop_launch(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=("simulation", "image"), default="simulation")
    args = parser.parse_args()
    os.environ["ROS_DOMAIN_ID"] = "190"
    os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"
    image = args.scenario == "image"
    directory = ROOT / "artifacts"
    directory.mkdir(exist_ok=True)
    command = ["ros2", "launch", "rover_autonomy", "simulation.launch.py"]
    if image:
        config = yaml.safe_load((ROOT / "src/rover_autonomy/config/rover.yaml").read_text())
        config["camera"]["source"] = str(ROOT / "tests/assets/palm_reference.png")
        config["hardware"]["enabled"] = False
        path = directory / "ros_image_smoke.yaml"
        path.write_text(yaml.safe_dump(config))
        command = [
            "ros2",
            "launch",
            "rover_autonomy",
            "rover.launch.py",
            "hardware_enabled:=false",
            "camera_backend:=image",
            f"config:={path}",
        ]
    report = {
        "scenario": args.scenario,
        "domain": 190,
        "hardware_output": False,
        "physical_camera": False,
        "range_is_virtual": True,
        "passed": False,
    }
    log = directory / f"pi_ros_{args.scenario}.log"
    node = None
    started = time.monotonic()
    process = None
    with log.open("w") as handle:
        rclpy.init()
        try:
            process = subprocess.Popen(
                command, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True
            )
            node = Probe(image)
            node.wait(
                lambda: bool(node.state) and bool(node.vision) and node.ranges > 0 and node.commands > 0
            )
            if node.state.get("armed"):
                raise AssertionError("Node started unexpectedly armed")
            mode = "hand" if image else "autonomous"
            node.mode.publish(String(data=mode))
            node.wait(lambda: node.state.get("mode") == mode and (not image or node.vision.get("hand")))
            node.call(node.arm, True)
            node.wait(lambda: node.max_linear > 0.001 or node.max_angular > 0.001)
            node.call(node.emergency, True)
            node.wait(
                lambda: (
                    node.state.get("emergency") and not node.state.get("armed") and node.command == (0.0, 0.0)
                )
            )
            deadline = time.monotonic() + 0.8
            while time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.05)
                if node.command != (0.0, 0.0):
                    raise AssertionError("Nonzero command during emergency stop")
            report.update(
                passed=True,
                commands=node.commands,
                vision_sequence=node.vision.get("sequence"),
                max_linear=node.max_linear,
                max_angular=node.max_angular,
                reasons=sorted(node.reasons),
                hand_detected=bool(node.vision.get("hand")),
            )
        except Exception as error:
            report["error"] = f"{type(error).__name__}: {error}"
        finally:
            try:
                if node is not None:
                    node.destroy_node()
            finally:
                if rclpy.ok():
                    rclpy.shutdown()
                if process is not None:
                    stop_launch(process)
    report["elapsed_seconds"] = time.monotonic() - started
    report["launch_exit_code"] = process.returncode if process is not None else None
    content = log.read_text()
    report["traceback_in_log"] = "Traceback (most recent call last)" in content
    if report["traceback_in_log"] or report["launch_exit_code"] != 0:
        report["passed"] = False
    (directory / f"pi_ros_{args.scenario}_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
