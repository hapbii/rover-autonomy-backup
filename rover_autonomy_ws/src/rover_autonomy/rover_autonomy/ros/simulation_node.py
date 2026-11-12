import math
import time
import uuid

import cv2
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Range
from std_msgs.msg import String

from rover_autonomy.ros.common import sensor_qos, spin_main, state_qos
from rover_autonomy.simulation import World
from rover_autonomy.transport import encode_vision
from rover_autonomy.types import Command, Hand, Line, Mode, Vision


class SimulationNode(Node):
    def __init__(self):
        super().__init__("rover_simulation")
        self.world = World()
        self.command = Command()
        self.command_at = -100.0
        self.previous = time.monotonic()
        self.mode = Mode.IDLE
        self.sequence = 0
        self.stream_id = uuid.uuid4().hex
        self.world.obstacle_enabled = self.declare_parameter("obstacle", False).value
        self.vision_pub = self.create_publisher(String, "/rover/vision", sensor_qos())
        self.range_pub = self.create_publisher(Range, "/rover/range", sensor_qos())
        self.odom_pub = self.create_publisher(Odometry, "/rover/odom", sensor_qos())
        self.image_pub = self.create_publisher(CompressedImage, "/rover/camera/compressed", sensor_qos())
        self.create_subscription(TwistStamped, "/rover/cmd_vel", self.on_command, 1)
        self.create_subscription(String, "/rover/active_mode", self.on_mode, state_qos())
        self.create_timer(0.05, self.tick)
        self.get_logger().info("SIMULATED camera observations, odometry and sonar; no hardware")

    def on_command(self, message):
        self.command = Command(message.twist.linear.x, message.twist.angular.z, "simulation")
        self.command_at = time.monotonic()

    def on_mode(self, message):
        try:
            self.mode = Mode(message.data)
        except ValueError:
            self.mode = Mode.IDLE

    def tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self.previous)
        self.previous = now
        self.world.advance(self.command if now - self.command_at < 0.3 else Command(), dt)
        stamp = self.get_clock().now().to_msg()
        self.sequence += 1
        hand = (
            Hand(0.3 * math.sin(now * 0.4), 0.025, 0.95, (120, 70, 40, 45))
            if self.mode == Mode.HAND
            else None
        )
        vision = Vision(
            self.sequence,
            now,
            Line(self.world.line_error(), 0.95),
            hand=hand,
            width=320,
            height=240,
            stream_id=self.stream_id,
        )
        stamp_ns = stamp.sec * 10**9 + stamp.nanosec
        self.vision_pub.publish(String(data=encode_vision(vision, now, stamp_ns)))
        distance = Range()
        distance.header.stamp = stamp
        distance.header.frame_id = "sonar_front"
        distance.radiation_type = Range.ULTRASOUND
        distance.field_of_view, distance.min_range, distance.max_range = 0.26, 0.02, 4.0
        distance.range = self.world.distance()
        self.range_pub.publish(distance)
        pose = Odometry()
        pose.header.stamp = stamp
        pose.header.frame_id, pose.child_frame_id = "odom", "base_link"
        pose.pose.pose.position.x, pose.pose.pose.position.y = self.world.x, self.world.y
        pose.pose.pose.orientation.z, pose.pose.pose.orientation.w = (
            math.sin(self.world.yaw / 2),
            math.cos(self.world.yaw / 2),
        )
        self.odom_pub.publish(pose)
        image = CompressedImage()
        image.header.stamp = stamp
        image.format = "jpeg"
        ok, encoded = cv2.imencode(".jpg", self.world.frame())
        if ok:
            image.data = encoded.tobytes()
            self.image_pub.publish(image)


def main(args=None):
    spin_main(SimulationNode, args)
