"""Finite EM2 PWM phases for two driver groups; no RPM/calibration claims."""

import math

READY = "EM2 READY 3 5 9 8 11 12 10"


def make_phases(pwm, duration):
    if isinstance(pwm, bool) or not isinstance(pwm, int) or not 1 <= pwm <= 80:
        raise ValueError("pwm must be an integer from 1 to 80 (out of 255)")
    return make_side_phases(pwm, pwm, duration)


def make_side_phases(right_pwm, left_pwm, duration):
    for name, value in (("right_pwm", right_pwm), ("left_pwm", left_pwm)):
        if isinstance(value, bool) or not isinstance(value, int) or not -80 <= value <= 80:
            raise ValueError(f"{name} must be an integer from -80 to 80")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or not 0.1 <= duration <= 1.5
    ):
        raise ValueError("duration must be between 0.1 and 1.5 seconds")
    return [
        ("initial_stop", 0, 0, 0.3),
        ("right_pair", right_pwm, 0, duration),
        ("stop_right", 0, 0, 0.3),
        ("left_pair", 0, left_pwm, duration),
        ("stop_left", 0, 0, 0.3),
        ("all_four", right_pwm, left_pwm, duration),
        ("final_stop", 0, 0, 0.3),
    ]


def parse_feedback(line):
    fields = line.split()
    if len(fields) != 3 or fields[0] != "T":
        raise ValueError("Bad EM2 feedback format")
    values = tuple(int(value) for value in fields[1:])
    if any(abs(value) > 80 for value in values):
        raise ValueError("Feedback outside firmware limits")
    return values
