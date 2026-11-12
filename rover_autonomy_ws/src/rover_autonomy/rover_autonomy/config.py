"""Configuration with validation before any hardware port can be opened."""

from dataclasses import asdict, dataclass, fields
from math import isfinite
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class ControllerConfig:
    cruise_speed: float = 0.10
    max_speed: float = 0.15
    max_angular: float = 0.7
    line_kp: float = 0.75
    heading_kp: float = 0.25
    line_min_confidence: float = 0.35
    camera_timeout: float = 0.55
    range_timeout: float = 0.40
    odometry_timeout: float = 0.40
    hard_stop_distance: float = 0.13
    obstacle_distance: float = 0.28
    clearance_distance: float = 0.42
    sign_confidence: float = 0.72
    sign_confirmations: int = 3
    sign_cooldown: float = 4.0
    turn_angle: float = 1.5707963267948966
    turn_tolerance: float = 0.10
    turn_timeout: float = 5.0
    scan_angle: float = 0.60
    scan_settle: float = 0.25
    bypass_distance: float = 0.30
    bypass_speed: float = 0.06
    bypass_timeout: float = 14.0
    bypass_extra_clearance: float = 0.25
    hand_min_confidence: float = 0.60
    hand_target_area: float = 0.045
    hand_stop_area: float = 0.075
    hand_target_distance: float = 0.55
    hand_stop_distance: float = 0.40
    hand_turn_kp: float = 0.9
    hand_forward_kp: float = 0.12

    def __post_init__(self):
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
                raise ValueError(f"{item.name} must be a finite number")
            if value <= 0:
                raise ValueError(f"{item.name} must be positive")
        if not isinstance(self.sign_confirmations, int) or self.sign_confirmations > 8:
            raise ValueError("sign_confirmations must be an integer from 1 to 8")
        if not self.hard_stop_distance < self.obstacle_distance < self.clearance_distance <= 4:
            raise ValueError("Distances must satisfy hard_stop < obstacle < clearance <= 4 m")
        if not self.hand_target_area < self.hand_stop_area < 1:
            raise ValueError("Require hand_target_area < hand_stop_area < 1")
        if not self.hand_stop_distance < self.hand_target_distance:
            raise ValueError("Hand stop distance must be below target distance")
        if self.cruise_speed > self.max_speed or self.bypass_speed > self.max_speed:
            raise ValueError("Cruise/bypass speeds cannot exceed max_speed")
        if self.max_speed > 0.5 or self.max_angular > 2.0:
            raise ValueError("Bench rover limits: max_speed <= 0.5 m/s, max_angular <= 2 rad/s")
        if any(
            getattr(self, key) > 1
            for key in ("line_min_confidence", "sign_confidence", "hand_min_confidence")
        ):
            raise ValueError("Confidence thresholds must be within (0, 1]")


@dataclass(frozen=True, slots=True)
class HardwareConfig:
    enabled: bool = False
    calibrated: bool = False
    port: str = "/dev/ttyACM0"
    baud: int = 115200
    wheel_radius_m: float = 0.0
    track_width_m: float = 0.0
    encoder_ticks_per_rev: int = 0
    encoder_signs: tuple[int, int, int, int] = (1, 1, 1, 1)  # LF RF LR RR
    max_rpm: float = 60.0
    max_pwm: int = 80
    pid_kp: float = 0.8
    pid_ki: float = 0.3
    pid_kd: float = 0.0
    feedforward: float = 1.1

    def __post_init__(self):
        if not isinstance(self.enabled, bool) or not isinstance(self.calibrated, bool):
            raise ValueError("enabled/calibrated must be YAML booleans")
        if not isinstance(self.port, str) or not self.port:
            raise ValueError("A serial port name is required")
        values = (
            self.wheel_radius_m,
            self.track_width_m,
            self.max_rpm,
            self.pid_kp,
            self.pid_ki,
            self.pid_kd,
            self.feedforward,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0
            for value in values
        ):
            raise ValueError("Hardware dimensions/gains must be finite nonnegative numbers")
        if (
            isinstance(self.encoder_ticks_per_rev, bool)
            or not isinstance(self.encoder_ticks_per_rev, int)
            or not 0 <= self.encoder_ticks_per_rev <= 100000
        ):
            raise ValueError("encoder_ticks_per_rev must be an integer (0 means uncalibrated)")
        if (
            not isinstance(self.encoder_signs, (tuple, list))
            or len(self.encoder_signs) != 4
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value not in (-1, 1)
                for value in self.encoder_signs
            )
        ):
            raise ValueError("encoder_signs must contain four integers, each +1 or -1")
        object.__setattr__(self, "encoder_signs", tuple(self.encoder_signs))
        if (
            isinstance(self.max_pwm, bool)
            or not isinstance(self.max_pwm, int)
            or not 1 <= self.max_pwm <= 100
        ):
            raise ValueError("max_pwm must be an integer from 1 to 100")

    def validate_for_motion(self):
        if not isinstance(self.enabled, bool) or not isinstance(self.calibrated, bool):
            raise ValueError("enabled/calibrated must be booleans")
        if not self.enabled or not self.calibrated:
            raise ValueError("Hardware output requires enabled=true and measured calibration")
        if not 0.005 <= self.wheel_radius_m <= 0.5 or not 0.03 <= self.track_width_m <= 2:
            raise ValueError("Measure wheel_radius_m and track_width_m before hardware output")
        if (
            isinstance(self.encoder_ticks_per_rev, bool)
            or not isinstance(self.encoder_ticks_per_rev, int)
            or not 1 <= self.encoder_ticks_per_rev <= 100000
        ):
            raise ValueError("Measure encoder x1 counts per output-shaft revolution")
        if len(self.encoder_signs) != 4 or any(
            isinstance(value, bool) or not isinstance(value, int) or value not in (-1, 1)
            for value in self.encoder_signs
        ):
            raise ValueError("Four encoder signs (+1 or -1) are required")
        values = (self.max_rpm, self.pid_kp, self.pid_ki, self.pid_kd, self.feedforward)
        if not all(
            not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value) and value >= 0
            for value in values
        ):
            raise ValueError("Hardware gains and RPM must be finite and nonnegative")
        if not 1 <= self.max_rpm <= 80 or not 1 <= self.max_pwm <= 100:
            raise ValueError("Hardware limits: max_rpm <= 80, max_pwm <= 100/255")
        if (
            isinstance(self.max_pwm, bool)
            or not isinstance(self.max_pwm, int)
            or self.pid_kp > 20
            or self.pid_ki > 20
            or self.pid_kd > 5
            or self.feedforward > 5
        ):
            raise ValueError("PID/PWM limits must match the RA1 firmware")
        if self.baud != 115200:
            raise ValueError("RA1 firmware uses 115200 baud")


def load_configuration(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as stream:
        result = yaml.safe_load(stream)
    if not isinstance(result, dict):
        raise ValueError("Configuration must be a YAML mapping")
    ControllerConfig(**result.get("controller", {}))
    HardwareConfig(**result.get("hardware", {}))
    return result


def controller_values() -> dict:
    return asdict(ControllerConfig())
