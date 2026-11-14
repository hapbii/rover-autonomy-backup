"""Pi-only camera ROS smoke. Starts camera_node only; no base, UART or motor output."""

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.environ["ROS_DOMAIN_ID"] = "191"
    log_path = ROOT / "artifacts/pi_ros_camera.log"
    log_path.parent.mkdir(exist_ok=True)
    process = node = None
    frames = []
    samples = []
    rclpy.init()
    try:
        node = Node("physical_camera_probe")

        def receive(message):
            image = cv2.imdecode(np.frombuffer(message.data, np.uint8), cv2.IMREAD_COLOR)
            if image is None or image.shape != (480, 640, 3):
                raise ValueError("Invalid camera JPEG")
            if len(frames) < 20:
                frames.append(time.monotonic())
                samples[:] = [image]

        node.create_subscription(
            CompressedImage, "/rover/camera/compressed", receive, qos_profile_sensor_data
        )
        with log_path.open("w") as log:
            process = subprocess.Popen(
                ["ros2", "run", "rover_autonomy", "camera_node"],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            deadline = time.monotonic() + 20
            while len(frames) < 20 and time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Camera node exited; inspect artifacts/pi_ros_camera.log")
                rclpy.spin_once(node, timeout_sec=0.1)
            if len(frames) < 20:
                raise TimeoutError("Camera topic did not provide 20 frames")
            assert cv2.imwrite(str(ROOT / "artifacts/pi_ros_camera_preview.jpg"), samples[0])
    finally:
        try:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
        finally:
            if node is not None:
                node.destroy_node()
            rclpy.shutdown()
    report = {
        "passed": len(frames) == 20 and process.returncode == 0,
        "physical_camera": True,
        "frames": len(frames),
        "fps": (len(frames) - 1) / (frames[-1] - frames[0]),
        "node_exit": process.returncode,
        "hardware_motor_output": False,
        "uart_opened": False,
    }
    (ROOT / "artifacts/pi_ros_camera_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
