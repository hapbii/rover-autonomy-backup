from dataclasses import dataclass
from math import cos, isfinite, pi, sin

from rover_autonomy.types import Odometry


def differential_rpm(
    linear: float, angular: float, radius: float, width: float, max_rpm: float
) -> tuple[float, float]:
    if (
        not all(isfinite(value) for value in (linear, angular, radius, width, max_rpm))
        or min(radius, width, max_rpm) <= 0
    ):
        raise ValueError("Kinematics requires finite values and positive measured geometry")
    right = (linear + angular * width / 2) / radius * 60 / (2 * pi)
    left = (linear - angular * width / 2) / radius * 60 / (2 * pi)
    # Common scaling preserves the requested curvature when either side saturates.
    scale = max(1.0, abs(right) / max_rpm, abs(left) / max_rpm)
    return right / scale, left / scale


def signed_count_delta(current: int, previous: int) -> int:
    # Unsigned uint32 firmware counters wrap in either direction.
    return ((current - previous + 2**31) % 2**32) - 2**31


@dataclass(slots=True)
class WheelOdometry:
    radius: float
    width: float
    ticks_per_rev: int
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    previous: tuple[int, int, int, int] | None = None

    def update(self, counts: tuple[int, int, int, int], now: float) -> Odometry:
        if self.previous is None:
            self.previous = counts
            return Odometry(self.x, self.y, self.yaw, now)
        if self.ticks_per_rev <= 0 or self.radius <= 0 or self.width <= 0:
            raise ValueError("Odometry requires measured geometry and encoder calibration")
        changes = [
            signed_count_delta(value, previous) for value, previous in zip(counts, self.previous, strict=True)
        ]
        self.previous = counts
        # Firmware counts are already signed/corrected: LF, RF, LR, RR.
        left = (changes[0] + changes[2]) / 2 * 2 * pi * self.radius / self.ticks_per_rev
        right = (changes[1] + changes[3]) / 2 * 2 * pi * self.radius / self.ticks_per_rev
        travel = (left + right) / 2
        turn = (right - left) / self.width
        self.x += travel * cos(self.yaw + turn / 2)
        self.y += travel * sin(self.yaw + turn / 2)
        self.yaw = (self.yaw + turn + pi) % (2 * pi) - pi
        return Odometry(self.x, self.y, self.yaw, now)
