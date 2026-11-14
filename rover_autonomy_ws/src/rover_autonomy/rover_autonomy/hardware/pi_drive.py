"""Coordinate sensor feedback, Pi PWM/PID and explicit reconnect/arm interlocks."""

from dataclasses import dataclass
from math import isfinite

from rover_autonomy.hardware.pi_motors import PiMotors, SpeedController
from rover_autonomy.hardware.sensor_protocol import SensorLink, signed_sequence_delta


@dataclass(frozen=True, slots=True)
class DriveTelemetry:
    sequence: int
    counts: tuple[int, int, int, int]
    right_rpm: float
    left_rpm: float
    right_pwm: int
    left_pwm: int
    range_mm: int
    flags: int
    ir_mask: int


class PiDriveLink:
    def __init__(self, port, config, now, *, sensors=None, motors=None):
        config.validate_for_motion()
        self.config = config
        self.motors = None
        self.sensors = None
        self.state = "boot"
        self.fault = ""
        self.latest = None
        self.previous = None
        self.wheel_rpm = (0.0,) * 4
        self.arm_requested = False
        self.saw_disarmed = False
        self.closed = False
        self.pid = SpeedController(config)
        self.last_tick = now
        try:
            self.motors = motors if motors is not None else PiMotors(config)
            self.sensors = sensors if sensors is not None else SensorLink(port, config, now)
        except BaseException:
            self.close()
            raise

    def set_arm(self, armed):
        if not armed:
            self.arm_requested = False
            self.saw_disarmed = True
            if self.state == "armed":
                self.state = "configured"
            self.pid.reset()
            if self.motors is not None:
                try:
                    self.motors.stop_outputs()
                except Exception as error:
                    self._fail(str(error))
        elif self.saw_disarmed and self.state == "configured":
            self.arm_requested = True

    def _fail(self, reason):
        self.fault = reason
        self.state = "fault"
        self.arm_requested = self.saw_disarmed = False
        self.pid.reset()
        try:
            self.motors.stop_outputs()
        except Exception as error:
            self.fault += f"; motor stop: {error}"

    def tick(self, now, right_rpm=0.0, left_rpm=0.0):
        if self.closed or self.state == "fault":
            return
        try:
            if now - self.last_tick > 0.24:
                raise ValueError("Pi control loop timeout; explicit reconnect/re-arm required")
            self.last_tick = now
            self.sensors.tick(now)
            if self.sensors.state == "fault":
                raise ValueError(self.sensors.fault)
            value = self.sensors.latest
            new_sample = value is not None and (
                self.previous is None or value.sequence != self.previous.sequence
            )
            dt = 0.0
            if new_sample and self.previous is not None:
                elapsed = signed_sequence_delta(value.sample_us, self.previous.sample_us)
                dt = elapsed / 1e6
                if not 0 < dt <= 0.2:
                    raise ValueError("Invalid encoder sampling interval")
                self.wheel_rpm = tuple(
                    signed_sequence_delta(current, old) * 60 / (self.config.encoder_ticks_per_rev * dt)
                    for current, old in zip(value.counts, self.previous.counts, strict=True)
                )
                if any(abs(rpm) > 2000 for rpm in self.wheel_rpm):
                    raise ValueError("Encoder RPM outside bounds")
            if self.sensors.state != "configured":
                self.state = self.sensors.state
            elif self.state != "armed":
                self.state = "configured"
            if self.arm_requested and self.state == "configured" and dt > 0:
                self.pid.reset()
                self.state = "armed"
            targets = (right_rpm, left_rpm)
            if not all(isfinite(x) and abs(x) <= self.config.max_rpm for x in targets):
                raise ValueError("Invalid target RPM")
            # Front range independently gates the final output, including direct cmd_vel input.
            can_move = (
                self.state == "armed"
                and self.arm_requested
                and value is not None
                and now - self.sensors.last_feedback <= 0.15
                and value.flags & 4
                and value.range_mm > 130
            )
            if not can_move:
                self.pid.reset()
                output = (0, 0)
            elif new_sample and dt > 0:
                output = self.pid.update(targets, self.wheel_rpm, dt, now)
            else:
                # A zero target must stop immediately even between encoder samples.
                output = tuple(0 if abs(targets[i]) < 0.01 else self.pid.applied[i] for i in range(2))
            self.motors.apply(*output)
            if value is not None:
                self.latest = DriveTelemetry(
                    value.sequence,
                    value.counts,
                    (self.wheel_rpm[1] + self.wheel_rpm[3]) / 2,
                    (self.wheel_rpm[0] + self.wheel_rpm[2]) / 2,
                    *output,
                    value.range_mm,
                    value.flags | int(self.state == "armed"),
                    value.ir_mask,
                )
            if new_sample:
                self.previous = value
        except Exception as error:
            self._fail(str(error))

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.state = "closed"
        self.arm_requested = self.saw_disarmed = False
        self.latest = self.previous = None
        motors, self.motors = self.motors, None
        sensors, self.sensors = self.sensors, None
        try:
            if motors is not None:
                motors.close()
        finally:
            if sensors is not None:
                sensors.close()
