"""Finite Pi GPIO PWM bench, gated by fresh RA2 sensor/range data."""

import sys
import time
from dataclasses import replace

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Int16MultiArray, String

from rover_autonomy.config import HardwareConfig
from rover_autonomy.hardware.bench import make_phases, make_side_phases
from rover_autonomy.hardware.pi_motors import PiMotors
from rover_autonomy.hardware.sensor_protocol import SensorLink
from rover_autonomy.ros.common import cleanup_signals, configuration


class MotorBenchTest(Node):
    def __init__(self):
        super().__init__("motor_bench_test")
        self.motors = self.sensors = None
        self.finished = self.success = False
        self.state = "boot"
        self.phase_index = 0
        self.phase_at = None
        try:
            if self.declare_parameter("wheels_lifted", False).value is not True:
                raise ValueError("Bench motion requires wheels_lifted:=true")
            settings, _ = configuration(self)
            self.config = replace(HardwareConfig(**settings.get("hardware", {})), enabled=True)
            port = self.declare_parameter("port", self.config.port).value
            pwm = self.declare_parameter("pwm", 48).value
            duration = self.declare_parameter("duration", 0.5).value
            right = self.declare_parameter("right_pwm", pwm).value
            left = self.declare_parameter("left_pwm", pwm).value
            make_phases(pwm, duration)
            self.phases = make_side_phases(right, left, duration)
            self.config = replace(self.config, max_pwm=max(self.config.max_pwm, abs(right), abs(left)))
            self.state_pub = self.create_publisher(String, "~/state", 10)
            self.feedback_pub = self.create_publisher(Int16MultiArray, "~/reported_pwm", 10)
            self.motors = PiMotors(self.config)
            now = time.monotonic()
            self.sensors = SensorLink(port, self.config, now)
            self.last_tick = now
            self.create_timer(0.05, self.tick)
            self.get_logger().info("Pi PWM0 left=12/18, PWM1 right=13/19; waiting for RA2 sensors")
        except BaseException:
            self.destroy_node()
            raise

    def fail(self, reason):
        self.finished = True
        self.success = False
        self.state = "fault"
        self.get_logger().error(reason)
        if self.motors is not None:
            self.motors.stop_outputs()

    def tick(self):
        if self.finished:
            return
        now = time.monotonic()
        try:
            if now - self.last_tick > 0.24:
                raise ValueError("Bench control loop timeout")
            self.last_tick = now
            self.sensors.tick(now)
            if self.sensors.state == "fault":
                raise ValueError(self.sensors.fault)
            if self.sensors.state != "configured":
                self.motors.apply(0, 0)
                return
            value = self.sensors.latest
            if value is None or now - self.sensors.last_feedback > 0.15 or not value.flags & 4:
                self.motors.apply(0, 0)
                if self.phase_at is not None:
                    raise ValueError("Range/telemetry lost during bench")
                return
            if value.range_mm <= 130:
                raise ValueError("Front range <= 130 mm; bench stopped")
            if self.phase_at is None:
                self.phase_at = now
            if now - self.phase_at >= self.phases[self.phase_index][3]:
                self.phase_index += 1
                self.phase_at = now
                if self.phase_index == len(self.phases):
                    self.motors.apply(0, 0)
                    self.finished = self.success = True
                    self.state = "complete"
                    self.state_pub.publish(
                        String(data="COMPLETE: GPIO stopped; verify shaft motion visually")
                    )
                    return
            label, right, left, _ = self.phases[self.phase_index]
            self.state = label
            self.motors.apply(right, left)
            self.feedback_pub.publish(Int16MultiArray(data=[right, left]))
            self.state_pub.publish(String(data=label))
        except Exception as error:
            self.fail(str(error))

    def destroy_node(self):
        motors, self.motors = self.motors, None
        sensors, self.sensors = self.sensors, None
        try:
            try:
                if motors is not None:
                    motors.close()
            finally:
                if sensors is not None:
                    sensors.close()
        finally:
            result = super().destroy_node()
        return result


def main(args=None):
    rclpy.init(args=args)
    node = None
    result = 1
    try:
        node = MotorBenchTest()
        while rclpy.ok() and not node.finished:
            rclpy.spin_once(node, timeout_sec=0.1)
        result = 0 if node.success else 1
    except (KeyboardInterrupt, ExternalShutdownException):
        result = 130
    except Exception as error:
        print(f"Motor bench failed: {error}", file=sys.stderr)
    finally:
        with cleanup_signals():
            try:
                if node is not None:
                    node.destroy_node()
            finally:
                if rclpy.ok():
                    rclpy.shutdown()
    return result
