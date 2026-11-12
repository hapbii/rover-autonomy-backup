"""Reactive, front-sonar-only obstacle bypass; not a map-based path planner."""

from math import atan2, cos, hypot, sin

from rover_autonomy.config import ControllerConfig
from rover_autonomy.types import Command, Odometry, Range


def angle_error(target: float, current: float) -> float:
    return atan2(sin(target - current), cos(target - current))


class Avoidance:
    def __init__(self, config: ControllerConfig):
        self.config = config
        self.reset()

    def reset(self):
        self.state = "idle"
        self.reference = 0.0
        self.target = 0.0
        self.started_at = 0.0
        self.phase_at = 0.0
        self.left_distance = 0.0
        self.right_distance = 0.0
        self.side = 1
        self.origin = (0.0, 0.0)
        self.required_travel = self.config.bypass_distance

    def begin(self, now: float, odometry: Odometry, front_distance: float = 0.0):
        self.reset()
        self.state = "scan_left"
        self.reference = odometry.yaw
        self.target = self.reference + self.config.scan_angle
        self.started_at = self.phase_at = now
        # Pass the original obstruction before steering back toward the line.
        # A fixed short detour can turn directly back into the obstacle.
        self.required_travel = max(
            self.config.bypass_distance,
            (front_distance + self.config.bypass_extra_clearance) / max(0.5, cos(self.config.scan_angle)),
        )

    def _turn(self, odometry: Odometry, now: float, next_state: str) -> Command:
        if now - self.phase_at > self.config.turn_timeout:
            self.state = "failed"
            return Command(reason="avoid_turn_timeout")
        error = angle_error(self.target, odometry.yaw)
        if abs(error) <= self.config.turn_tolerance:
            self.state = next_state
            self.phase_at = now
            if next_state == "advance":
                self.origin = (odometry.x, odometry.y)
            return Command(reason=f"avoid_{next_state}")
        speed = min(self.config.max_angular, max(0.20, abs(error) * 1.8))
        return Command(angular=speed if error > 0 else -speed, reason=f"avoid_{self.state}")

    def tick(self, now: float, odometry: Odometry, distance: Range, line_visible: bool) -> Command:
        if now - self.started_at > 30 and self.state not in ("idle", "done", "failed"):
            self.state = "failed"
        if self.state == "failed":
            return Command(reason="avoid_failed_rearm_required")
        if self.state == "scan_left":
            return self._turn(odometry, now, "sample_left")
        if self.state == "sample_left":
            if distance.sampled_at < self.phase_at + self.config.scan_settle:
                return Command(reason="avoid_settle_left")
            self.left_distance = distance.distance_m
            self.state = "scan_right"
            self.target = self.reference - self.config.scan_angle
            self.phase_at = now
            return Command(reason="avoid_scan_right")
        if self.state == "scan_right":
            return self._turn(odometry, now, "sample_right")
        if self.state == "sample_right":
            if distance.sampled_at < self.phase_at + self.config.scan_settle:
                return Command(reason="avoid_settle_right")
            self.right_distance = distance.distance_m
            if max(self.left_distance, self.right_distance) < self.config.clearance_distance:
                self.state = "failed"
                return Command(reason="avoid_both_sides_blocked")
            self.side = 1 if self.left_distance >= self.right_distance else -1
            self.target = self.reference + self.side * self.config.scan_angle
            self.state = "orient"
            self.phase_at = now
            return Command(reason="avoid_choose_clear_side")
        if self.state == "orient":
            return self._turn(odometry, now, "advance")
        if self.state == "advance":
            travelled = hypot(odometry.x - self.origin[0], odometry.y - self.origin[1])
            if distance.distance_m < self.config.obstacle_distance:
                self.state = "failed"
                return Command(reason="avoid_new_obstacle")
            if now - self.phase_at > self.config.bypass_timeout:
                self.state = "failed"
                return Command(reason="avoid_no_progress")
            if travelled >= self.required_travel:
                self.state = "return_heading"
                self.target = self.reference
                self.phase_at = now
                return Command(reason="avoid_return_heading")
            return Command(linear=self.config.bypass_speed, reason="avoid_advance")
        if self.state == "return_heading":
            return self._turn(odometry, now, "reacquire")
        if self.state == "reacquire":
            if line_visible:
                self.state = "done"
                return Command(reason="avoid_line_reacquired")
            if now - self.phase_at > 1.5:
                self.state = "failed"
                return Command(reason="avoid_line_not_found")
            return Command(angular=-self.side * 0.25, reason="avoid_search_line")
        return Command(reason=f"avoid_{self.state}")
