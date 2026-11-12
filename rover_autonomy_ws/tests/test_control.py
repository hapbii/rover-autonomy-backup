import math
from dataclasses import replace

import pytest
from rover_autonomy.control.avoidance import Avoidance, angle_error
from rover_autonomy.control.supervisor import Supervisor
from rover_autonomy.simulation import World
from rover_autonomy.types import Detection, Hand, Line, Mode, Odometry, Range, Sign, Vision

from rover_autonomy.config import ControllerConfig


def ready(mode=Mode.AUTONOMOUS, now=10.0):
    controller = Supervisor()
    controller.set_mode(mode)
    controller.set_armed(True)
    update(controller, now)
    return controller


def update(controller, now, line=None, signs=(), hand=None, distance=2.0, yaw=0.0, seq=None, x=0.0, y=0.0):
    sequence = int(now * 1000) if seq is None else seq
    controller.update_vision(Vision(sequence, now, line or Line(0, 0.9), signs, hand, 320, 240, "test"))
    controller.update_range(Range(distance, now))
    controller.update_odometry(Odometry(x, y, yaw, now))


def sign(label):
    return (Detection(label, 0.98, (100, 20, 40, 80)),)


def test_default_is_disarmed_and_mode_change_does_not_arm():
    controller = Supervisor()
    assert controller.tick(10).stopped
    controller.set_mode(Mode.AUTONOMOUS)
    assert controller.tick(10).stopped


@pytest.mark.parametrize("error,expected_sign", [(-0.5, 1), (0.5, -1)])
def test_camera_line_steering(error, expected_sign):
    controller = ready()
    update(controller, 10.1, line=Line(error, 0.9))
    command = controller.tick(10.1)
    assert command.linear > 0
    assert command.angular * expected_sign > 0


@pytest.mark.parametrize("source", ["camera", "range", "future_camera", "invalid_range"])
def test_sensor_faults_override_motion(source):
    controller = ready()
    if source == "camera":
        controller.update_range(Range(2, 11))
        now = 11
    elif source == "range":
        controller.update_vision(Vision(20000, 11, Line(0, 1), width=320, height=240, stream_id="test"))
        now = 11
    elif source == "future_camera":
        controller.update_vision(Vision(20000, 20, Line(0, 1), width=320, height=240, stream_id="test"))
        now = 10.1
    else:
        controller.update_range(Range(float("nan"), 10.1))
        now = 10.1
    assert controller.tick(now).stopped


def test_duplicate_camera_frame_does_not_refresh_watchdog():
    controller = ready()
    update(controller, 11, seq=10000)
    assert controller.tick(11).reason == "camera_stale"


def test_camera_restart_with_new_stream_can_recover_without_replaying_sign_evidence():
    controller = ready()
    controller.update_vision(Vision(1, 10.2, Line(0, 1), width=320, height=240, stream_id="new_session"))
    controller.update_range(Range(2, 10.2))
    assert controller.tick(10.2).linear > 0


def test_red_latches_and_needs_three_unique_green_frames():
    controller = ready()
    update(controller, 10.1, signs=sign(Sign.RED))
    assert controller.tick(10.1).reason == "red_light_stop"
    update(controller, 10.2)
    assert controller.tick(10.2).reason == "red_light_stop"
    update(controller, 10.3, signs=sign(Sign.GREEN))
    assert controller.tick(10.3).stopped
    assert controller.tick(10.31).stopped
    update(controller, 10.4, signs=sign(Sign.GREEN))
    assert controller.tick(10.4).stopped
    update(controller, 10.5, signs=sign(Sign.GREEN))
    assert controller.tick(10.5).linear > 0


def test_red_wins_over_simultaneous_green():
    controller = ready()
    update(controller, 10.1, signs=sign(Sign.RED) + sign(Sign.GREEN))
    assert controller.tick(10.1).reason == "red_light_stop"


@pytest.mark.parametrize("label,direction", [(Sign.LEFT, 1), (Sign.RIGHT, -1)])
def test_arrow_turns_use_odometry_and_do_not_repeat(label, direction):
    controller = ready()
    for index in range(3):
        now = 10.1 + index * 0.1
        update(controller, now, signs=sign(label))
        result = controller.tick(now)
    assert result.reason == "sign_turn_start"
    update(controller, 10.4, signs=sign(label))
    assert controller.tick(10.4).angular * direction > 0
    update(controller, 10.5, signs=sign(label), yaw=direction * math.pi / 2)
    assert controller.tick(10.5).reason == "sign_turn_complete"
    update(controller, 10.6, signs=sign(label), yaw=direction * math.pi / 2)
    assert controller.tick(10.6).reason == "camera_line_follow"


def test_arrow_turn_timeout_stays_stopped_until_rearmed():
    controller = ready()
    for now in (10.1, 10.2, 10.3):
        update(controller, now, signs=sign(Sign.LEFT))
        controller.tick(now)
    update(controller, 16, signs=sign(Sign.LEFT))
    assert controller.tick(16).stopped
    update(controller, 16.1)
    assert controller.tick(16.1).reason == "sign_turn_failed_rearm_required"
    controller.set_armed(False)
    controller.set_armed(True)
    assert controller.tick(16.1).linear > 0


def test_angle_wraparound():
    assert angle_error(-math.pi + 0.1, math.pi - 0.1) == pytest.approx(0.2)


@pytest.mark.parametrize(
    "center,area,expected",
    [
        (-0.3, 0.015, "approach_left"),
        (0.3, 0.015, "approach_right"),
        (0.0, 0.09, "stop"),
        (0.8, 0.015, "rotate_only"),
    ],
)
def test_hand_follow_outputs(center, area, expected):
    controller = ready(Mode.HAND)
    update(controller, 10.1, hand=Hand(center, area, 0.95, (50, 40, 30, 40)))
    command = controller.tick(10.1)
    if expected == "approach_left":
        assert command.linear > 0 and command.angular > 0
    elif expected == "approach_right":
        assert command.linear > 0 and command.angular < 0
    elif expected == "rotate_only":
        assert command.linear == 0 and command.angular < 0
    else:
        assert command.stopped


def test_lost_hand_stops_and_never_reverses_to_chase():
    controller = ready(Mode.HAND)
    update(controller, 10.1)
    assert controller.tick(10.1).reason == "hand_lost"
    update(controller, 10.2, hand=Hand(0, 0.06, 0.9, (0, 0, 30, 30)))
    assert controller.tick(10.2).linear == 0
    update(controller, 10.3, hand=Hand(0, 0.015, 0.9, (0, 0, 30, 30)), distance=0.2)
    assert controller.tick(10.3).reason == "hand_obstacle_stop"


def test_calibrated_hand_distance_stops_when_close():
    controller = ready(Mode.HAND)
    update(controller, 10.1, hand=Hand(0, 0.02, 0.9, (1, 1, 30, 30), 0.35))
    assert controller.tick(10.1).reason == "hand_too_close"


def test_red_interrupts_avoidance():
    controller = ready()
    update(controller, 10.1, distance=0.25)
    assert controller.tick(10.1).angular > 0
    update(controller, 10.2, signs=sign(Sign.RED), distance=0.25)
    assert controller.tick(10.2).reason == "red_light_stop"
    assert controller.avoidance.state == "idle"


def test_both_blocked_cannot_choose_a_random_side():
    avoidance = Avoidance(ControllerConfig())
    avoidance.begin(10, Odometry(0, 0, 0, 10))
    avoidance.tick(10.1, Odometry(0, 0, 0.6, 10.1), Range(0.2, 10.1), True)
    avoidance.tick(10.5, Odometry(0, 0, 0.6, 10.5), Range(0.2, 10.5), True)
    avoidance.tick(10.6, Odometry(0, 0, -0.6, 10.6), Range(0.2, 10.6), True)
    result = avoidance.tick(11, Odometry(0, 0, -0.6, 11), Range(0.2, 11), True)
    assert result.stopped and avoidance.state == "failed"


def test_closed_loop_obstacle_scan_and_bypass():
    controller = ready(now=0)
    world = World(obstacle_enabled=True)
    phases = set()
    minimum = 4.0
    for step in range(600):
        now = (step + 1) * 0.05
        distance = world.distance()
        minimum = min(minimum, distance)
        update(
            controller,
            now,
            line=Line(world.line_error(), 0.95),
            distance=distance,
            yaw=world.yaw,
            x=world.x,
            y=world.y,
        )
        command = controller.tick(now)
        phases.add(controller.avoidance.state)
        world.advance(command, 0.05)
    assert "scan_left" in phases and "scan_right" in phases
    assert "advance" in phases and "done" in phases
    assert "failed" not in phases
    assert minimum > controller.config.hard_stop_distance


@pytest.mark.parametrize(
    "changes",
    [
        {"max_speed": -1},
        {"max_speed": float("nan")},
        {"hand_stop_area": 0.01},
        {"sign_confirmations": 0},
        {"hard_stop_distance": 0.5},
    ],
)
def test_invalid_controller_config(changes):
    with pytest.raises(ValueError):
        replace(ControllerConfig(), **changes)
