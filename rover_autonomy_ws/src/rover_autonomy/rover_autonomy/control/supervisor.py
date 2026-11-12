"""One authority for motion: stop conditions precede every behavior."""

from math import isfinite

from rover_autonomy.config import ControllerConfig
from rover_autonomy.control.avoidance import Avoidance, angle_error
from rover_autonomy.control.sign_filter import SignFilter
from rover_autonomy.types import Command, Mode, Odometry, Range, Sign, Vision


class Supervisor:
    def __init__(self, config: ControllerConfig | None = None):
        self.config = config or ControllerConfig()
        self.mode = Mode.IDLE
        self.armed = False
        self.emergency = False
        self.vision: Vision | None = None
        self.distance: Range | None = None
        self.odometry: Odometry | None = None
        self.signs = SignFilter(self.config.sign_confirmations, self.config.sign_confidence)
        self.avoidance = Avoidance(self.config)
        self.turn_target: float | None = None
        self.turn_started = 0.0
        self.last_arrow = Sign.NONE
        self.arrow_last_visible = -100.0
        self.arrow_last_action = -100.0
        self.turn_failed = False

    def set_mode(self, mode: str | Mode):
        self.mode = Mode(mode)
        self._reset_maneuvers()

    def set_armed(self, armed: bool):
        self.armed = bool(armed)
        if not self.armed:
            self._reset_maneuvers()

    def _reset_maneuvers(self):
        self.avoidance.reset()
        self.turn_target = None
        self.turn_failed = False
        self.last_arrow = Sign.NONE

    def update_vision(self, vision: Vision):
        # Do not let duplicate or reordered messages refresh the camera watchdog.
        changed_stream = (
            self.vision is not None
            and vision.stream_id != self.vision.stream_id
            and vision.captured_at > self.vision.captured_at
        )
        if changed_stream:
            self.signs.history.clear()
            self.signs.last_sequence = -1
            self.signs.confirmed = Sign.NONE
            self._reset_maneuvers()
        if (
            self.vision is None
            or changed_stream
            or (vision.stream_id == self.vision.stream_id and vision.sequence > self.vision.sequence)
        ):
            self.vision = vision

    def update_range(self, distance: Range):
        if self.distance is None or distance.sampled_at > self.distance.sampled_at:
            self.distance = distance

    def update_odometry(self, odometry: Odometry):
        if self.odometry is None or odometry.sampled_at > self.odometry.sampled_at:
            self.odometry = odometry

    def odometry_valid(self, now: float) -> bool:
        value = self.odometry
        return (
            value is not None
            and all(isfinite(x) for x in (value.x, value.y, value.yaw, value.sampled_at))
            and 0 <= now - value.sampled_at <= self.config.odometry_timeout
        )

    def tick(self, now: float) -> Command:
        if not isfinite(now):
            return Command(reason="invalid_clock")
        if self.emergency:
            return Command(reason="emergency_stop")
        if not self.armed or self.mode == Mode.IDLE:
            return Command(reason="disarmed" if not self.armed else "idle")
        vision = self.vision
        if (
            vision is None
            or not isfinite(vision.captured_at)
            or not 0 <= now - vision.captured_at <= self.config.camera_timeout
        ):
            return Command(reason="camera_stale")
        self.signs.observe(vision.sequence, vision.signs)
        if self.signs.red_latched:
            self.turn_target = None
            self.avoidance.reset()
            return Command(reason="red_light_stop")
        distance = self.distance
        if distance is None or not distance.valid(now, self.config.range_timeout):
            return Command(reason="range_stale_or_invalid")
        if distance.distance_m <= self.config.hard_stop_distance:
            return Command(reason="obstacle_hard_stop")
        if self.mode == Mode.HAND:
            return self._hand_command(vision, distance)
        line = vision.line
        line_valid = (
            all(isfinite(value) for value in (line.error, line.confidence, line.heading))
            and abs(line.error) <= 1
            and 0 <= line.confidence <= 1
            and abs(line.heading) <= 1
        )
        line_visible = line_valid and line.confidence >= self.config.line_min_confidence
        active_avoidance = self.avoidance.state not in ("idle", "done")
        if distance.distance_m <= self.config.obstacle_distance or active_avoidance:
            if not self.odometry_valid(now):
                return Command(reason="odometry_required_for_avoidance")
            self.turn_target = None
            if self.avoidance.state in ("idle", "done"):
                self.avoidance.begin(now, self.odometry, distance.distance_m)
            return self.avoidance.tick(now, self.odometry, distance, line_visible)
        if self.mode == Mode.AUTONOMOUS:
            turn = self._sign_command(now, vision)
            if turn is not None:
                return turn
        if not line_visible:
            return Command(reason="line_lost")
        angular = -self.config.line_kp * line.error + self.config.heading_kp * line.heading
        angular = max(-self.config.max_angular, min(self.config.max_angular, angular))
        speed = self.config.cruise_speed * max(0.25, 1 - abs(angular) / self.config.max_angular * 0.65)
        return Command(speed, angular, "camera_line_follow")

    def _sign_command(self, now: float, vision: Vision) -> Command | None:
        labels = {item.label for item in vision.signs if item.confidence >= self.config.sign_confidence}
        if self.last_arrow in labels:
            self.arrow_last_visible = now
        elif now - self.arrow_last_visible > 1.0:
            self.last_arrow = Sign.NONE
        if self.turn_failed:
            return Command(reason="sign_turn_failed_rearm_required")
        if self.turn_target is not None:
            if not self.odometry_valid(now):
                return Command(reason="odometry_stale_during_turn")
            error = angle_error(self.turn_target, self.odometry.yaw)
            if abs(error) <= self.config.turn_tolerance:
                self.turn_target = None
                return Command(reason="sign_turn_complete")
            if now - self.turn_started > self.config.turn_timeout:
                self.turn_failed = True
                return Command(reason="sign_turn_timeout")
            angular = min(self.config.max_angular, max(0.2, abs(error) * 1.8))
            return Command(angular=angular if error > 0 else -angular, reason="sign_turn")
        confirmed = self.signs.confirmed
        if (
            confirmed in (Sign.LEFT, Sign.RIGHT)
            and confirmed != self.last_arrow
            and now - self.arrow_last_action >= self.config.sign_cooldown
        ):
            if not self.odometry_valid(now):
                return Command(reason="odometry_required_for_sign_turn")
            self.last_arrow = confirmed
            self.arrow_last_visible = self.arrow_last_action = now
            self.turn_target = (
                self.odometry.yaw + (1 if confirmed == Sign.LEFT else -1) * self.config.turn_angle
            )
            self.turn_started = now
            return Command(reason="sign_turn_start")
        return None

    def _hand_command(self, vision: Vision, distance: Range) -> Command:
        hand = vision.hand
        if hand is None or not all(isfinite(value) for value in (hand.center_x, hand.area, hand.confidence)):
            return Command(reason="hand_lost")
        if (
            not -1 <= hand.center_x <= 1
            or not 0 < hand.area <= 1
            or not self.config.hand_min_confidence <= hand.confidence <= 1
        ):
            return Command(reason="hand_invalid")
        if distance.distance_m <= self.config.obstacle_distance:
            return Command(reason="hand_obstacle_stop")
        if hand.area >= self.config.hand_stop_area:
            return Command(reason="hand_too_close")
        if hand.distance_m is not None:
            if not isfinite(hand.distance_m) or hand.distance_m <= 0:
                return Command(reason="hand_distance_invalid")
            if hand.distance_m <= self.config.hand_stop_distance:
                return Command(reason="hand_too_close")
            approach = max(0.0, (hand.distance_m - self.config.hand_target_distance) * 0.35)
            distance_mode = "calibrated_palm_width"
        else:
            # Relative-size following, not an uncalibrated claim of metric hand distance.
            approach = max(
                0.0, ((self.config.hand_target_area / hand.area) ** 0.5 - 1) * self.config.hand_forward_kp
            )
            distance_mode = "relative_palm_size"
        angular = max(
            -self.config.max_angular, min(self.config.max_angular, -self.config.hand_turn_kp * hand.center_x)
        )
        speed = min(self.config.max_speed, approach) * max(0.0, 1 - abs(hand.center_x) * 1.8)
        if abs(hand.center_x) > 0.55:
            speed = 0.0
        return Command(speed, angular, f"hand_follow_{distance_mode}")

    def status(self) -> dict:
        return {
            "mode": self.mode.value,
            "armed": self.armed,
            "emergency": self.emergency,
            "red_latched": self.signs.red_latched,
            "avoidance": self.avoidance.state,
            "sign_turn_active": self.turn_target is not None,
            "turn_failed": self.turn_failed,
        }
