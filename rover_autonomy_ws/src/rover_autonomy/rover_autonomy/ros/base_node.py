import json
import time
from dataclasses import replace
from math import cos, isfinite, sin

from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from sensor_msgs.msg import Range
from std_msgs.msg import Bool, Float64MultiArray, Int16MultiArray, String, UInt32MultiArray

from rover_autonomy.config import HardwareConfig
from rover_autonomy.hardware.kinematics import WheelOdometry, differential_rpm
from rover_autonomy.hardware.pi_drive import PiDriveLink
from rover_autonomy.ros.common import configuration, sensor_qos, spin_main, state_qos


class BaseNode(Node):
    def __init__(self):
        super().__init__("rover_base")
        settings, _ = configuration(self)
        values = dict(settings.get("hardware", {}))
        if "encoder_signs" in values:
            values["encoder_signs"] = tuple(values["encoder_signs"])
        self.config = HardwareConfig(**values)
        enabled = self.declare_parameter("hardware_enabled", self.config.enabled).value
        self.config = replace(self.config, enabled=enabled)
        self.link = None
        self.link_fault = ""
        self.retry_at = 0.0
        self.command_at = -100.0
        self.command = (0.0, 0.0)
        self.arm = False
        self.need_disarm = False
        self.last_telemetry = None
        self.odom = None
        if enabled:
            self.config.validate_for_motion()
            self.odom = WheelOdometry(
                self.config.wheel_radius_m, self.config.track_width_m, self.config.encoder_ticks_per_rev
            )
        self.rpm_pub = self.create_publisher(Float64MultiArray, "/rover/target_rpm", 1)
        self.measured_rpm_pub = self.create_publisher(Float64MultiArray, "/rover/measured_rpm", sensor_qos())
        self.counts_pub = self.create_publisher(UInt32MultiArray, "/rover/encoder_counts", sensor_qos())
        self.pwm_pub = self.create_publisher(Int16MultiArray, "/rover/applied_pwm", sensor_qos())
        self.ir_pub = self.create_publisher(Int16MultiArray, "/rover/ir", sensor_qos())
        self.ir_raw_pub = self.create_publisher(Int16MultiArray, "/rover/ir_raw", sensor_qos())
        self.range_pub = self.create_publisher(Range, "/rover/range", sensor_qos())
        self.odom_pub = self.create_publisher(Odometry, "/rover/odom", sensor_qos())
        self.state_pub = self.create_publisher(String, "/rover/base_state", state_qos())
        self.create_subscription(TwistStamped, "/rover/cmd_vel", self.on_command, 1)
        self.create_subscription(Bool, "/rover/armed", self.on_arm, state_qos())
        self.create_timer(0.05, self.tick)
        self.create_timer(0.2, self.publish_state)
        self.get_logger().info("LIVE PI PWM + UNO SENSORS" if enabled else "DRY RUN: no GPIO/serial opened")

    def on_command(self, message):
        age = (
            self.get_clock().now().nanoseconds
            - message.header.stamp.sec * 10**9
            - message.header.stamp.nanosec
        ) / 1e9
        linear, angular = message.twist.linear.x, message.twist.angular.z
        if (
            not 0 <= age <= 0.25
            or not all(isfinite(value) for value in (linear, angular))
            or abs(linear) > 0.5
            or abs(angular) > 2
        ):
            self.command = (0.0, 0.0)
            self.need_disarm = True
            self.arm = False
            return
        self.command = (linear, angular)
        self.command_at = time.monotonic() - age

    def on_arm(self, message):
        if not message.data:
            self.arm = False
            self.need_disarm = False
            if self.link is not None:
                self.link.set_arm(False)
        elif not self.need_disarm:
            self.arm = True

    def tick(self):
        now = time.monotonic()
        linear, angular = self.command
        if now - self.command_at > 0.25:
            linear = angular = 0.0
            if self.arm:
                self.need_disarm = True
                self.arm = False
        if not self.arm or self.need_disarm:
            linear = angular = 0.0
        if not self.config.enabled:
            # Keep units honest; without measured geometry no wheel RPM can be derived.
            preview = [0.0, 0.0]
            if self.config.wheel_radius_m > 0 and self.config.track_width_m > 0:
                preview = list(
                    differential_rpm(
                        linear,
                        angular,
                        self.config.wheel_radius_m,
                        self.config.track_width_m,
                        self.config.max_rpm,
                    )
                )
            self.rpm_pub.publish(Float64MultiArray(data=preview))
            return
        if self.link is None and now >= self.retry_at:
            try:
                self.link = PiDriveLink(self.config.port, self.config, now)
                self.link_fault = ""
                self.last_telemetry = None
                self.odom.previous = None
                self.need_disarm = True
            except (OSError, ValueError) as error:
                self.link_fault = str(error)
                self.retry_at = now + 2
                self.get_logger().error(self.link_fault, throttle_duration_sec=2.0)
        if self.link is None:
            return
        try:
            self.link.set_arm(self.arm and not self.need_disarm)
        except Exception as error:
            self.link._fail(str(error))
        telemetry = self.link.latest
        # A fresh command alone cannot bypass a missing/too-close front range reading.
        if telemetry is None or not telemetry.flags & 4 or telemetry.range_mm <= 130:
            linear = angular = 0.0
        right, left = differential_rpm(
            linear, angular, self.config.wheel_radius_m, self.config.track_width_m, self.config.max_rpm
        )
        self.rpm_pub.publish(Float64MultiArray(data=[right, left]))
        self.link.tick(now, right, left)
        if self.link.state == "fault":
            self.link_fault = self.link.fault
            self.close_link()
            self.arm = False
            self.need_disarm = True
            self.retry_at = now + 2
            return
        value = self.link.latest
        if value is not None and value.sequence != self.last_telemetry:
            self.last_telemetry = value.sequence
            self.publish_telemetry(value, now)

    def publish_telemetry(self, value, now):
        self.measured_rpm_pub.publish(Float64MultiArray(data=[value.right_rpm, value.left_rpm]))
        self.counts_pub.publish(UInt32MultiArray(data=list(value.counts)))
        self.pwm_pub.publish(Int16MultiArray(data=[value.right_pwm, value.left_pwm]))
        raw_ir = [int(bool(value.ir_mask & (1 << i))) for i in range(5)]
        self.ir_raw_pub.publish(Int16MultiArray(data=raw_ir))
        self.ir_pub.publish(
            Int16MultiArray(data=[int(bool(raw) != self.config.ir_active_low) for raw in raw_ir])
        )
        stamp = self.get_clock().now().to_msg()
        distance = Range()
        distance.header.stamp = stamp
        distance.header.frame_id = "sonar_front"
        distance.radiation_type = Range.ULTRASOUND
        distance.field_of_view = 0.26
        distance.min_range, distance.max_range = 0.02, 4.0
        distance.range = value.range_mm / 1000 if value.flags & 4 else float("nan")
        self.range_pub.publish(distance)
        pose = self.odom.update(value.counts, now)
        message = Odometry()
        message.header.stamp = stamp
        message.header.frame_id = "odom"
        message.child_frame_id = "base_link"
        message.pose.pose.position.x, message.pose.pose.position.y = pose.x, pose.y
        message.pose.pose.orientation.z, message.pose.pose.orientation.w = (
            sin(pose.yaw / 2),
            cos(pose.yaw / 2),
        )
        right = value.right_rpm * 2 * 3.141592653589793 * self.config.wheel_radius_m / 60
        left = value.left_rpm * 2 * 3.141592653589793 * self.config.wheel_radius_m / 60
        message.twist.twist.linear.x = (right + left) / 2
        message.twist.twist.angular.z = (right - left) / self.config.track_width_m
        self.odom_pub.publish(message)

    def publish_state(self):
        state = (
            "dry_run"
            if not self.config.enabled
            else self.link.state
            if self.link is not None
            else "disconnected"
        )
        data = {
            "state": state,
            "hardware_enabled": self.config.enabled,
            "fault": self.link_fault,
            "need_disarm": self.need_disarm,
        }
        self.state_pub.publish(String(data=json.dumps(data, allow_nan=False)))

    def close_link(self):
        link, self.link = self.link, None
        if link is not None:
            try:
                link.close()
            except (OSError, ValueError) as error:
                self.get_logger().warning(f"Serial close failed: {error}")

    def destroy_node(self):
        try:
            self.close_link()
        finally:
            result = super().destroy_node()
        return result


def main(args=None):
    spin_main(BaseNode, args)
