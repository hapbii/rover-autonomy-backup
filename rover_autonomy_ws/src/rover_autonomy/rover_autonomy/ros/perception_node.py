import time
import uuid
from dataclasses import replace

import cv2
import numpy as np
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Image
from std_msgs.msg import String

from rover_autonomy.hardware.images import decode_raw_image
from rover_autonomy.ros.common import configuration, sensor_qos, spin_main, state_qos
from rover_autonomy.transport import encode_vision
from rover_autonomy.types import Mode
from rover_autonomy.vision.hands import PalmDetector
from rover_autonomy.vision.line import LineConfig
from rover_autonomy.vision.pipeline import PerceptionPipeline


class PerceptionNode(Node):
    def __init__(self):
        super().__init__("rover_perception")
        self.pipeline = None
        self.palm = None
        self.latest = None
        self.mode = Mode.IDLE
        self.sequence = 0
        self.stream_id = uuid.uuid4().hex
        config, share = configuration(self)
        settings = config.get("perception", {})
        try:
            cv2.setNumThreads(1)
            palm = PalmDetector(
                share / "models/palm_detection_mediapipe_2023feb.onnx",
                confidence=float(settings.get("palm_confidence", 0.65)),
                calibrated_fx=float(settings.get("calibrated_fx", 0)),
                calibrated_image_width=int(settings.get("calibrated_image_width", 640)),
                palm_width_m=float(settings.get("palm_width_m", 0)),
            )
            self.palm = palm
            line = LineConfig(
                roi_top=float(settings.get("roi_top", 0.58)),
                dark_line=bool(settings.get("dark_line", True)),
                threshold=int(settings.get("line_threshold", 75)),
            )
            self.pipeline = PerceptionPipeline(
                line,
                palm,
                settings.get("experimental_sign_model_path"),
                settings.get("sign_backend", "geometry"),
            )
            self.publisher = self.create_publisher(String, "/rover/vision", sensor_qos())
            self.image_transport = settings.get("image_transport", "compressed")
            if self.image_transport not in ("compressed", "raw"):
                raise ValueError("image_transport must be compressed or raw")
            message_type = CompressedImage if self.image_transport == "compressed" else Image
            topic = settings.get("image_topic", "/rover/camera/compressed")
            self.create_subscription(message_type, topic, self.on_image, sensor_qos())
            self.create_subscription(String, "/rover/active_mode", self.on_mode, state_qos())
            fps = float(settings.get("fps", 8))
            if not 1 <= fps <= 20:
                raise ValueError("Perception FPS must be between 1 and 20")
            self.create_timer(1 / fps, self.tick)
        except BaseException:
            self.destroy_node()
            raise

    def on_image(self, message):
        if len(message.data) <= 4_000_000:
            self.latest = message  # Replace, never append frames to a queue.

    def on_mode(self, message):
        try:
            self.mode = Mode(message.data)
        except ValueError:
            self.mode = Mode.IDLE

    def tick(self):
        message, self.latest = self.latest, None
        if message is None:
            return
        stamp_ns = message.header.stamp.sec * 10**9 + message.header.stamp.nanosec
        age = (self.get_clock().now().nanoseconds - stamp_ns) / 1e9
        if not 0 <= age <= 0.5:
            return
        try:
            if self.image_transport == "raw":
                frame = decode_raw_image(
                    message.data, message.width, message.height, message.step, message.encoding
                )
            else:
                frame = cv2.imdecode(np.frombuffer(message.data, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                return
            captured_at = time.monotonic() - age
            self.sequence += 1
            result = self.pipeline.process(frame, self.sequence, captured_at, self.mode == Mode.HAND)
            result = replace(result, stream_id=self.stream_id)
            self.publisher.publish(String(data=encode_vision(result, time.monotonic(), stamp_ns)))
        except (ValueError, RuntimeError, cv2.error) as error:
            self.get_logger().error(str(error), throttle_duration_sec=2.0)

    def destroy_node(self):
        self.latest = None
        pipeline, self.pipeline = self.pipeline, None
        palm, self.palm = self.palm, None
        try:
            if pipeline is not None:
                pipeline.close()
            elif palm is not None:
                palm.close()
        finally:
            result = super().destroy_node()
        return result


def main(args=None):
    spin_main(PerceptionNode, args)
