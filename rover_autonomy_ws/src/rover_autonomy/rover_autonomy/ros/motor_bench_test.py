"""Finite four-motor/two-driver bench test for matching Uno EM2 firmware.

Open-loop PWM only. T messages acknowledge firmware output settings, not shaft motion.
"""

import math
import sys
import time

import rclpy
import serial
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Int16MultiArray, String

from rover_autonomy.hardware.bench import READY, make_phases, make_side_phases, parse_feedback
from rover_autonomy.ros.common import cleanup_signals


class MotorBenchTest(Node):
    def __init__(self):
        super().__init__("motor_bench_test")
        self.ser = None
        self.confirmed = False
        try:
            self.initialize()
        except BaseException:
            self.destroy_node()
            raise

    def initialize(self):
        dp = self.declare_parameter
        if dp("wheels_lifted", False).value is not True:
            raise ValueError("Bench motion requires wheels_lifted:=true and reachable motor power cutoff")
        port = dp("port", "/dev/ttyACM0").value
        pwm = dp("pwm", 48).value
        duration = dp("duration", 0.5).value
        right_pwm = dp("right_pwm", pwm).value
        left_pwm = dp("left_pwm", pwm).value
        stby_pin = dp("stby_pin", 10).value
        if isinstance(stby_pin, bool) or stby_pin != 10:
            raise ValueError("Current bench wiring requires STBY=D10")
        self.expected_ready = READY
        self.boot_wait = dp("boot_wait", 2.0).value
        self.handshake_timeout = dp("handshake_timeout", 5.0).value
        make_phases(pwm, duration)  # Preserve validation of the legacy common-PWM option.
        self.phases = make_side_phases(right_pwm, left_pwm, duration)
        if (
            isinstance(self.boot_wait, bool)
            or not math.isfinite(self.boot_wait)
            or not 0 <= self.boot_wait <= 5
        ):
            raise ValueError("boot_wait must be between 0 and 5 seconds")
        if (
            isinstance(self.handshake_timeout, bool)
            or not math.isfinite(self.handshake_timeout)
            or not 0.5 <= self.handshake_timeout <= 10
        ):
            raise ValueError("handshake_timeout must be between 0.5 and 10 seconds")
        self.state_pub = self.create_publisher(String, "~/state", 10)
        self.feedback_pub = self.create_publisher(Int16MultiArray, "~/reported_pwm", 10)
        self.finished = False
        self.success = False
        self.confirmed = False
        self.state = "boot"
        self.rx = bytearray()
        self.start_time = time.monotonic()
        self.last_hello = 0.0
        self.last_feedback = 0.0
        self.phase_index = 0
        self.phase_at = 0.0
        self.phase_ack = False
        self.stop_at = 0.0
        self.arm_sent_at = 0.0
        self.expected = (0, 0)
        self.ser = serial.Serial(port, 115200, timeout=0, write_timeout=0.1, exclusive=True)
        self.timer = self.create_timer(0.05, self.tick)
        self.get_logger().info(
            f"Port {port}; A/right PWM={right_pwm}, B/left PWM={left_pwm}; STBY=D{stby_pin}; {duration}s per phase. No encoder measurement."
        )

    def send(self, command):
        data = (command + "\n").encode("ascii")
        if self.ser.write(data) != len(data):
            raise serial.SerialException("Incomplete serial write")

    def fail(self, reason):
        if self.finished:
            return
        self.get_logger().error(reason)
        self.state_pub.publish(String(data="FAILED: " + reason))
        self.finished = True
        self.success = False
        self.stop_best_effort()

    def stop_best_effort(self):
        if self.confirmed and self.ser is not None and self.ser.is_open:
            try:
                self.send("STOP")
            except (OSError, serial.SerialException):
                pass

    def enter_phase(self, now):
        label, a, b, _ = self.phases[self.phase_index]
        self.expected = (a, b)
        self.phase_at = now
        self.phase_ack = False
        self.get_logger().info(f"{label}: PWM A={a}, B={b}")
        self.state_pub.publish(String(data=label))

    def receive(self, line, now):
        if self.finished:
            return
        if line.startswith("EM2 READY"):
            if line != self.expected_ready:
                self.fail("Firmware pin mapping does not match the configured wiring")
            elif self.state == "handshake":
                self.confirmed = True
                self.send("ARM")
                self.arm_sent_at = now
                self.state = "arming"
            else:
                self.fail("Unexpected firmware identification during test; stopped")
        elif line.startswith("RA1 READY"):
            self.fail("RA1 firmware needs measured RPM calibration; this raw-PWM bench requires EM2 firmware")
        elif line == "EM2 ARMED" and self.state == "arming":
            self.state = "running"
            self.last_feedback = now
            self.enter_phase(now)
        elif line == "EM2 STOPPED" and self.state == "stopping":
            self.success = self.finished = True
            self.get_logger().info(
                "TEST COMPLETE: firmware acknowledged A, B, both and STOP. Shaft motion is not measured."
            )
            self.state_pub.publish(String(data="COMPLETE: stopped; no encoder feedback"))
        elif line.startswith("T ") and self.confirmed:
            try:
                values = parse_feedback(line)
            except ValueError as exc:
                self.fail(str(exc))
                return
            self.last_feedback = now
            self.feedback_pub.publish(Int16MultiArray(data=list(values)))
            if self.state == "running" and values == self.expected:
                self.phase_ack = True
        elif line.startswith("EM2 ERROR") or line == "EM2 TIMEOUT":
            self.fail("Arduino fault: " + line)
        elif line == "EM2 BOOT" and self.confirmed:
            self.fail("Arduino reset during test")

    def tick(self):
        if self.finished:
            return
        now = time.monotonic()
        try:
            self.rx.extend(self.ser.read(1024))
            while b"\n" in self.rx:
                raw, _, rest = self.rx.partition(b"\n")
                self.rx = bytearray(rest)
                if len(raw) > 256:
                    self.fail("Serial line too long")
                    return
                self.receive(raw.decode("ascii", errors="replace").strip(), now)
                if self.finished:
                    return
            if len(self.rx) > 256:
                self.fail("Serial buffer overflow")
                return
            if self.state == "boot":
                if now - self.start_time < self.boot_wait:
                    return
                self.state = "handshake"
            if self.state == "handshake":
                if now - self.start_time > self.boot_wait + self.handshake_timeout:
                    self.fail("Matching EM2 firmware not detected; no motor command sent")
                elif now - self.last_hello >= 0.5:
                    self.send("HELLO")
                    self.last_hello = now
            elif self.state == "arming":
                if now - self.arm_sent_at > 2.0:
                    self.fail("No ARM acknowledgement")
            elif self.state == "running":
                if now - self.last_feedback > 0.4:
                    self.fail("Arduino feedback lost; stopping")
                    return
                if now - self.phase_at >= self.phases[self.phase_index][3]:
                    if not self.phase_ack:
                        self.fail("Output setting was not acknowledged for this phase")
                        return
                    self.phase_index += 1
                    if self.phase_index == len(self.phases):
                        self.send("STOP")
                        self.state = "stopping"
                        self.stop_at = now
                        return
                    self.enter_phase(now)
                a, b = self.expected
                self.send(f"M {a} {b}")
            elif self.state == "stopping" and now - self.stop_at > 1.0:
                self.fail("No STOP acknowledgement")
        except (OSError, serial.SerialException) as exc:
            self.fail(f"Serial failure: {exc}")

    def destroy_node(self):
        try:
            self.stop_best_effort()
        finally:
            connection, self.ser = self.ser, None
            try:
                if connection is not None:
                    connection.close()
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
    except (ValueError, OSError, serial.SerialException) as exc:
        print(f"Motor bench test failed: {exc}", file=sys.stderr)
    finally:
        with cleanup_signals():
            try:
                if node is not None:
                    node.destroy_node()
            finally:
                if rclpy.ok():
                    rclpy.shutdown()
    return result
