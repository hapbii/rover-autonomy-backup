import json
import time
from math import atan2

from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry as OdometryMsg
from rclpy.node import Node
from sensor_msgs.msg import Range as RangeMsg
from std_msgs.msg import Bool, String
from std_srvs.srv import SetBool

from rover_autonomy.config import ControllerConfig
from rover_autonomy.control.supervisor import Supervisor
from rover_autonomy.ros.common import configuration, sensor_qos, spin_main, state_qos
from rover_autonomy.transport import decode_vision
from rover_autonomy.types import Command, Mode, Odometry, Range


class SupervisorNode(Node):
    def __init__(self):
        super().__init__("rover_supervisor")
        config, _ = configuration(self)
        self.controller = Supervisor(ControllerConfig(**config.get("controller", {})))
        self.hardware_enabled = self.declare_parameter("hardware_enabled", False).value
        self.base_ready = not self.hardware_enabled
        self.last_reason = ""
        self.publisher = self.create_publisher(TwistStamped, "/rover/cmd_vel", 1)
        self.state_pub = self.create_publisher(String, "/rover/state", state_qos())
        self.armed_pub = self.create_publisher(Bool, "/rover/armed", state_qos())
        self.mode_pub = self.create_publisher(String, "/rover/active_mode", state_qos())
        self.create_subscription(String, "/rover/vision", self.on_vision, sensor_qos())
        self.create_subscription(RangeMsg, "/rover/range", self.on_range, sensor_qos())
        self.create_subscription(OdometryMsg, "/rover/odom", self.on_odometry, sensor_qos())
        self.create_subscription(String, "/rover/mode", self.on_mode, 1)
        self.create_subscription(String, "/rover/base_state", self.on_base, state_qos())
        self.create_service(SetBool, "/rover/arm", self.on_arm)
        self.create_service(SetBool, "/rover/emergency_stop", self.on_emergency)
        self.create_timer(0.05, self.tick)
        self.create_timer(0.2, self.publish_state)

    def on_vision(self, message):
        try:
            self.controller.update_vision(
                decode_vision(message.data, time.monotonic(), self.get_clock().now().nanoseconds)
            )
        except (KeyError, TypeError, ValueError) as error:
            self.get_logger().warning(f"Rejected vision packet: {error}", throttle_duration_sec=2.0)

    def age(self, stamp):
        return (self.get_clock().now().nanoseconds - (stamp.sec * 10**9 + stamp.nanosec)) / 1e9

    def on_range(self, message):
        age = self.age(message.header.stamp)
        if 0 <= age <= 1:
            self.controller.update_range(Range(float(message.range), time.monotonic() - age))

    def on_odometry(self, message):
        age = self.age(message.header.stamp)
        if not 0 <= age <= 1:
            return
        position = message.pose.pose.position
        q = message.pose.pose.orientation
        yaw = atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))
        self.controller.update_odometry(Odometry(position.x, position.y, yaw, time.monotonic() - age))

    def on_mode(self, message):
        self.publish_command(Command(reason="mode_change"))
        try:
            self.controller.set_mode(message.data)
        except ValueError:
            self.controller.set_armed(False)
            self.controller.set_mode(Mode.IDLE)
            self.get_logger().warning("Invalid mode; allowed: idle, autonomous, line, hand")

    def on_base(self, message):
        if not self.hardware_enabled:
            return
        try:
            if len(message.data) > 4096:
                return
            value = json.loads(message.data)
            if not isinstance(value, dict):
                raise ValueError("Base state must be an object")
            self.base_ready = value.get("state") in ("configured", "armed") and not value.get("fault")
            if value.get("fault"):
                self.controller.set_armed(False)
        except (ValueError, TypeError):
            self.base_ready = False

    def on_arm(self, request, response):
        if request.data:
            now = time.monotonic()
            vision = self.controller.vision
            distance = self.controller.distance
            ready = (
                self.base_ready
                and not self.controller.emergency
                and vision is not None
                and 0 <= now - vision.captured_at <= self.controller.config.camera_timeout
                and distance is not None
                and distance.valid(now, self.controller.config.range_timeout)
            )
            if not ready:
                response.success = False
                response.message = "Need fresh camera/range, configured base, and released emergency stop"
                return response
        self.controller.set_armed(request.data)
        self.publish_command(Command(reason="arm_change"))
        self.publish_state()
        response.success = True
        response.message = "armed" if request.data else "disarmed"
        return response

    def on_emergency(self, request, response):
        self.controller.emergency = request.data
        self.controller.set_armed(False)
        self.publish_command(Command(reason="emergency_change"))
        self.publish_state()
        response.success = True
        response.message = "Emergency state changed; explicit re-arm is required"
        return response

    def publish_command(self, command):
        if not self.context.ok():
            return
        value = TwistStamped()
        value.header.stamp = self.get_clock().now().to_msg()
        value.header.frame_id = "base_link"
        value.twist.linear.x = command.linear
        value.twist.angular.z = command.angular
        self.publisher.publish(value)

    def tick(self):
        command = self.controller.tick(time.monotonic())
        self.publish_command(command)
        if command.reason != self.last_reason:
            self.last_reason = command.reason
            self.get_logger().info(command.reason)

    def publish_state(self):
        if not self.context.ok():
            return
        self.armed_pub.publish(Bool(data=self.controller.armed and not self.controller.emergency))
        self.mode_pub.publish(String(data=self.controller.mode.value))
        state = self.controller.status() | {"reason": self.last_reason}
        self.state_pub.publish(String(data=json.dumps(state, allow_nan=False)))

    def destroy_node(self):
        try:
            if hasattr(self, "controller"):
                self.controller.set_armed(False)
                self.publish_command(Command(reason="shutdown"))
                self.publish_state()
        finally:
            result = super().destroy_node()
        return result


def main(args=None):
    spin_main(SupervisorNode, args)
