import pytest
from rover_autonomy.hardware.bench import make_phases, make_side_phases, parse_feedback


def test_bench_runs_right_pair_left_pair_all_four_then_zero():
    phases = make_phases(48, 0.5)
    moving = [(label, right, left) for label, right, left, _ in phases if right or left]
    assert moving == [("right_pair", 48, 0), ("left_pair", 0, 48), ("all_four", 48, 48)]
    assert phases[0][1:3] == phases[-1][1:3] == (0, 0)


def test_longest_sequence_finishes_before_firmware_eight_second_session():
    assert sum(item[3] for item in make_phases(80, 1.5)) < 8


def test_separate_side_direction_and_pwm():
    assert make_side_phases(40, -50, 0.5)[5][1:3] == (40, -50)


@pytest.mark.parametrize("pwm", [True, 0, -1, 81, 48.5, float("nan")])
def test_invalid_pwm_never_forms_motion_phases(pwm):
    with pytest.raises(ValueError):
        make_phases(pwm, 0.5)


@pytest.mark.parametrize("duration", [True, 0, -1, 1.6, float("nan"), float("inf")])
def test_invalid_duration(duration):
    with pytest.raises(ValueError):
        make_phases(48, duration)


@pytest.mark.parametrize("packet", ["T 81 0", "T 0 -81", "T nan 0", "T 0 0 0", "X 0 0"])
def test_invalid_feedback(packet):
    with pytest.raises(ValueError):
        parse_feedback(packet)


def test_feedback_reports_setting_not_motion():
    assert parse_feedback("T 48 -48") == (48, -48)
