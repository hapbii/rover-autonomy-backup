"""Pi 4 dual-channel hardware PWM, independent A/B directions and daemon watchdog."""

import math
import time
from pathlib import Path

from rover_autonomy.config import HardwareConfig

SCRIPT_MARKER = 1380927058


def watchdog_script(standby_pins):
    left, right = standby_pins
    # p0 is refreshed only by successful control ticks. p9 latches a timeout.
    # This script lives in pigpiod, so loss of the Python process does not keep STBY high.
    return f"""ld v0 p0
ld v1 0
tag 0
mils 10
lda p0
cmp v0
jz 1
ld v0 p0
ld v1 0
tag 1
inr v1
lda v1
cmp 25
jm 0
ld p9 1
w {left} 0
w {right} 0
halt
"""


class PiMotors:
    def __init__(self, config: HardwareConfig, client=None, clock=time.monotonic):
        self.config = config
        self.clock = clock
        self.script_id = None
        self.closed = False
        self.last_output = (0, 0)
        self.counter = 0
        self.lock = None
        self.pi = client
        try:
            if client is None:
                import fcntl

                # Held for the connection's entire lifetime; bench and base cannot fight GPIO.
                self.lock = open(Path("/tmp/rover-autonomy-motors.lock"), "a+")
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                model = Path("/proc/device-tree/model").read_text().rstrip("\0")
                if "Raspberry Pi 4" not in model:
                    raise ValueError("This PWM backend targets Pi 4; confirm board model first")
                import pigpio

                self.pi = pigpio.pi("localhost", 8888)
            if not self.pi.connected:
                self.pi.stop()
                self.pi = None
                raise OSError("Local pigpiod is unavailable; start it with the default PCM clock")
            # Disable both drivers before configuring any direction or PWM pin.
            for pin in config.standby_pins:
                self._call("write", pin, 0)
                self._call("set_mode", pin, 1)
                self._call("set_pull_up_down", pin, 1)  # PUD_DOWN
            for pin in (*config.left_direction_pins, *config.right_direction_pins):
                self._call("write", pin, 0)
                self._call("set_mode", pin, 1)
            for pin in (*config.left_pwm_pins, *config.right_pwm_pins):
                self._call("hardware_PWM", pin, config.pwm_frequency, 0)
            if self.lock is not None:
                # Reap our stored watchdog after a previous process was killed.
                self.lock.seek(0)
                old = self.lock.read().strip()
                if old.isdecimal():
                    try:
                        status, params = self.pi.script_status(int(old))
                    except Exception:
                        # Daemon restart invalidates script IDs; no old script remains to reap.
                        status, params = -1, ()
                    if status >= 0 and len(params) == 10 and params[8] == SCRIPT_MARKER:
                        self._call("stop_script", int(old))
                        self._call("delete_script", int(old))
            self.script_id = self._call("store_script", watchdog_script(config.standby_pins))
            if self.lock is not None:
                self.lock.seek(0)
                self.lock.truncate()
                self.lock.write(str(self.script_id))
                self.lock.flush()
            # pigpio initializes stored scripts asynchronously.
            deadline = self.clock() + 1.0
            while self.pi.script_status(self.script_id)[0] == 0:
                if self.clock() >= deadline:
                    raise OSError("pigpiod watchdog initialization timeout")
                time.sleep(0.01)
            self._call("run_script", self.script_id, [0] * 8 + [SCRIPT_MARKER])
            deadline = self.clock() + 1.0
            while self.pi.script_status(self.script_id)[0] not in (2, 3):
                if self.clock() >= deadline:
                    raise OSError("pigpiod watchdog did not start")
                time.sleep(0.01)
            self.last_update = self.clock()
        except BaseException:
            self.close()
            raise

    def _call(self, method, *args):
        value = getattr(self.pi, method)(*args)
        if isinstance(value, int) and value < 0:
            raise OSError(f"pigpio {method} failed: {value}")
        return value

    def apply(self, right, left):
        if self.closed:
            raise OSError("Motor outputs closed")
        try:
            if any(type(value) is not int or abs(value) > self.config.max_pwm for value in (right, left)):
                raise ValueError("PWM outside configured limit (units out of 255)")
            if self.clock() - self.last_update >= 0.24:
                raise OSError("Motor control heartbeat expired")
            status, params = self.pi.script_status(self.script_id)
            if status not in (2, 3) or params[9]:
                raise OSError("Motor watchdog stopped/expired; reconnect and explicitly re-arm")
            # Only blank STBY during output changes; leave steady hardware PWM undisturbed.
            if (right, left) != self.last_output:
                self.stop_outputs()
                for pwm, pins, indices in (
                    (left, self.config.left_direction_pins, (0, 2)),
                    (right, self.config.right_direction_pins, (1, 3)),
                ):
                    for channel, motor_index in enumerate(indices):
                        signed = pwm * self.config.motor_signs[motor_index]
                        self._call("write", pins[2 * channel], int(signed > 0))
                        self._call("write", pins[2 * channel + 1], int(signed < 0))
                for pwm, pins in ((left, self.config.left_pwm_pins), (right, self.config.right_pwm_pins)):
                    duty = round(abs(pwm) * 1000000 / 255)
                    for pin in pins:
                        self._call("hardware_PWM", pin, self.config.pwm_frequency, duty)
            status, params = self.pi.script_status(self.script_id)
            if status not in (2, 3) or params[9] or self.clock() - self.last_update >= 0.24:
                raise OSError("Motor watchdog expired during output update")
            self.counter = (self.counter + 1) % (2**31)
            self._call("update_script", self.script_id, [self.counter])
            self._call("write", self.config.standby_pins[0], int(left != 0))
            self._call("write", self.config.standby_pins[1], int(right != 0))
            self.last_output = (right, left)
            self.last_update = self.clock()
        except BaseException:
            self.stop_outputs()
            raise

    def stop_outputs(self):
        self.last_output = (0, 0)
        if self.pi is None:
            return
        error = None
        # Attempt every stop even if one pigpio operation fails.
        for method, args in [
            *(("write", (pin, 0)) for pin in self.config.standby_pins),
            *(
                ("hardware_PWM", (pin, self.config.pwm_frequency, 0))
                for pin in (*self.config.left_pwm_pins, *self.config.right_pwm_pins)
            ),
        ]:
            try:
                self._call(method, *args)
            except Exception as exc:
                error = exc
        if error is not None:
            raise OSError(f"Motor stop failed: {error}") from error

    def close(self):
        if self.closed:
            return
        try:
            self.stop_outputs()
        finally:
            self.closed = True
            if self.pi is not None:
                try:
                    if self.script_id is not None:
                        self._call("stop_script", self.script_id)
                        self._call("delete_script", self.script_id)
                        if self.lock is not None:
                            self.lock.seek(0)
                            self.lock.truncate()
                            self.lock.flush()
                finally:
                    try:
                        self.pi.stop()
                    finally:
                        if self.lock is not None:
                            self.lock.close()
                            self.lock = None
            elif self.lock is not None:
                self.lock.close()
                self.lock = None


class SpeedController:
    """Two side PIDs with per-wheel stall/direction checks (LF RF LR RR)."""

    def __init__(self, config):
        self.config = config
        self.reset()

    def reset(self):
        self.integrals = [0.0, 0.0]
        self.errors = [0.0, 0.0]
        self.stall_since = [None] * 4
        self.reverse_since = [None] * 4
        self.applied = (0, 0)

    def update(self, targets, wheel_rpm, dt, now):
        if not 0 < dt <= 0.2 or not all(math.isfinite(x) for x in (*targets, *wheel_rpm)):
            raise ValueError("Invalid PID sample")
        if any(abs(value) > self.config.max_rpm for value in targets):
            raise ValueError("Invalid target RPM")
        measured = ((wheel_rpm[1] + wheel_rpm[3]) / 2, (wheel_rpm[0] + wheel_rpm[2]) / 2)
        for index, rpm in enumerate(wheel_rpm):
            side = 0 if index in (1, 3) else 1
            stall = abs(targets[side]) > 8 and abs(self.applied[side]) > 45 and abs(rpm) < 1
            reverse = abs(rpm) > 10 and targets[side] * rpm < 0
            for condition, values, seconds, label in (
                (stall, self.stall_since, 0.5, "individual encoder stall"),
                (reverse, self.reverse_since, 0.25, "individual encoder direction"),
            ):
                values[index] = (now if values[index] is None else values[index]) if condition else None
                if values[index] is not None and now - values[index] > seconds:
                    raise ValueError(label)
        outputs = []
        for side, target in enumerate(targets):
            if abs(target) < 0.01:
                self.integrals[side] = self.errors[side] = 0
                outputs.append(0)
                continue
            error = target - measured[side]
            integral = max(-100, min(100, self.integrals[side] + error * dt))
            raw = (
                self.config.feedforward * target
                + self.config.pid_kp * error
                + self.config.pid_ki * integral
                + self.config.pid_kd * (error - self.errors[side]) / dt
            )
            limited = max(-self.config.max_pwm, min(self.config.max_pwm, raw))
            if limited == raw or raw * error <= 0:
                self.integrals[side] = integral
            self.errors[side] = error
            outputs.append(round(limited))
        self.applied = tuple(outputs)
        return self.applied
