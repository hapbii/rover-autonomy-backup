from dataclasses import replace

import pytest
from rover_autonomy.hardware.pi_drive import PiDriveLink
from rover_autonomy.hardware.pi_motors import PiMotors, SpeedController
from rover_autonomy.hardware.sensor_protocol import READY, SensorLink, parse_telemetry

from rover_autonomy.config import HardwareConfig


def calibrated():
    return HardwareConfig(
        enabled=True, calibrated=True, wheel_radius_m=0.03, track_width_m=0.2, encoder_ticks_per_rev=1000
    )


class Wire:
    def __init__(self):
        self.incoming = bytearray()
        self.commands = []
        self.closed = False

    def inject(self, text):
        self.incoming.extend(text.encode())

    def read(self, size):
        result = self.incoming[:size]
        del self.incoming[:size]
        return bytes(result)

    def write(self, data):
        self.commands.append(data.decode().strip())
        return len(data)

    def close(self):
        self.closed = True


def sensor_ready():
    wire = Wire()
    sensor = SensorLink("fake", calibrated(), 0, wire)
    sensor.tick(2.1)
    wire.inject(READY + "\n")
    sensor.tick(2.2)
    wire.inject("RA2 CONFIGURED\nS 0 100000 0 0 0 0 1200 4 31\n")
    sensor.tick(2.3)
    assert sensor.state == "configured"
    return sensor, wire


def packet(seq, *, counts=(0, 0, 0, 0), distance=1200, flags=4, stamp=None):
    return (
        f"S {seq} {stamp if stamp is not None else 100000 + seq * 50000} "
        + " ".join(map(str, (*counts, distance, flags, 21)))
        + "\n"
    )


def test_sensor_handshake_only_configures_signs_and_never_sends_motor_commands():
    sensor, wire = sensor_ready()
    assert wire.commands == ["HELLO", "CFG 1 1 1 1"]
    assert sensor.latest.counts == (0, 0, 0, 0)
    sensor.close()
    assert wire.closed and sensor.transport is None and not sensor.buffer


@pytest.mark.parametrize(
    "line",
    [
        "RA1 READY CAMERA_US 3 5 9 8 11 12 10\n",
        "EM2 READY 3 5 9 8 11 12 10\n",
        READY + "\n",
        "RA2 BOOT\n",
        "S 1 150000 0 0 0 0 nan 4 0\n",
        "x" * 201,
        "S 1 150000 0 0 0 0 -1 4 0\n",
        "S 1 150000 0 0 0 0 1200 0 0\n",
        "S 1 150000 0 0 0 0 1200 4 32\n",
        "unexpected\n",
    ],
)
def test_old_firmware_restarts_and_malformed_packets_fault(line):
    sensor, wire = sensor_ready()
    wire.inject(line)
    sensor.tick(2.35)
    assert sensor.state == "fault"
    assert not any(command.startswith(("ARM", "V ", "M ")) for command in wire.commands)


def test_fragmented_packets_and_raw_ir_polarity():
    sensor, wire = sensor_ready()
    wire.inject("S 1 150000 4294967295 ")
    sensor.tick(2.35)
    wire.inject("1 2 3 1200 4 21\n")
    sensor.tick(2.4)
    assert sensor.latest.counts == (2**32 - 1, 1, 2, 3)
    assert sensor.latest.ir_values() == (0, 1, 0, 1, 0)
    assert sensor.latest.ir_values(False) == (1, 0, 1, 0, 1)


def test_duplicates_do_not_refresh_sensor_timeout():
    sensor, wire = sensor_ready()
    wire.inject(packet(0))
    sensor.tick(2.7)
    assert sensor.state == "fault" and "timeout" in sensor.fault


def test_sensor_clock_and_sequence_wrap_are_accepted():
    sensor, wire = sensor_ready()
    sensor.latest = parse_telemetry("S 4294967295 4294967290 0 0 0 0 1000 4 0")
    wire.inject(packet(0, stamp=49994))
    sensor.tick(2.35)
    assert sensor.state == "configured" and sensor.latest.sample_us == 49994


class Motors:
    def __init__(self):
        self.output = (0, 0)
        self.closed = False

    def apply(self, *output):
        self.output = output

    def stop_outputs(self):
        self.output = (0, 0)

    def close(self):
        self.stop_outputs()
        self.closed = True


def drive_ready():
    sensor, wire = sensor_ready()
    motors = Motors()
    drive = PiDriveLink("fake", calibrated(), 2.3, sensors=sensor, motors=motors)
    drive.tick(2.3)
    return drive, wire, motors


def arm_drive(drive, wire):
    drive.set_arm(False)
    drive.set_arm(True)
    wire.inject(packet(1))
    drive.tick(2.35, 40, 20)
    assert drive.state == "armed"


def test_no_motor_output_until_explicit_disarm_arm_and_fresh_encoder_pair():
    drive, wire, motors = drive_ready()
    drive.set_arm(True)
    wire.inject(packet(1))
    drive.tick(2.35, 40, 20)
    assert drive.state == "configured" and motors.output == (0, 0)
    drive.set_arm(False)
    drive.set_arm(True)
    wire.inject(packet(2))
    drive.tick(2.4, 40, 20)
    assert drive.state == "armed" and motors.output[0] > motors.output[1] > 0
    assert wire.commands == ["HELLO", "CFG 1 1 1 1"]


@pytest.mark.parametrize("distance,flags", [(130, 4), (50, 4), (-1, 0)])
def test_hard_range_gate_stops_pi_pwm(distance, flags):
    drive, wire, motors = drive_ready()
    arm_drive(drive, wire)
    wire.inject(packet(2, distance=distance, flags=flags))
    drive.tick(2.4, 40, 40)
    assert motors.output == (0, 0)


def test_zero_command_stops_between_encoder_reports():
    drive, wire, motors = drive_ready()
    arm_drive(drive, wire)
    assert motors.output != (0, 0)
    drive.tick(2.37, 0, 0)
    assert motors.output == (0, 0)


@pytest.mark.parametrize("failure", ["serial", "loop", "restart", "target", "sample_time"])
def test_faults_stop_and_require_a_new_connection(failure):
    drive, wire, motors = drive_ready()
    arm_drive(drive, wire)
    now, targets = 2.4, (40, 40)
    if failure == "loop":
        now = 2.7
    elif failure == "serial":
        wire.read = lambda _: (_ for _ in ()).throw(OSError("USB lost"))
    elif failure == "restart":
        wire.inject("RA2 BOOT\n")
    elif failure == "target":
        targets = (float("nan"), 40)
    else:
        wire.inject(packet(2, stamp=150000))
    drive.tick(now, *targets)
    assert drive.state == "fault" and motors.output == (0, 0)
    drive.set_arm(True)
    drive.tick(now + 0.05, 40, 40)
    assert drive.state == "fault" and motors.output == (0, 0)
    drive.close()
    assert motors.closed and wire.closed


def test_encoder_rpm_uses_uno_sample_interval_and_all_four_wheels():
    drive, wire, _ = drive_ready()
    wire.inject(packet(1, counts=(10, 20, 30, 40)))
    drive.tick(2.36)
    assert drive.wheel_rpm == pytest.approx((12, 24, 36, 48))
    assert drive.latest.right_rpm == 36 and drive.latest.left_rpm == 24


@pytest.mark.parametrize("wheel_rpm,label", [((0, 30, 30, 30), "stall"), ((-20, 30, 30, 30), "direction")])
def test_one_bad_encoder_cannot_hide_in_side_average(wheel_rpm, label):
    controller = SpeedController(calibrated())
    with pytest.raises(ValueError, match=label):
        for index in range(20):
            controller.update((50, 50), wheel_rpm, 0.05, index * 0.05)


class Pigpio:
    connected = True

    def __init__(self):
        self.calls = []
        self.parameters = [0] * 10
        self.stopped = False

    def script_status(self, _):
        return 2, self.parameters[:]

    def stop(self):
        self.stopped = True

    def __getattr__(self, name):
        def call(*args):
            self.calls.append((name, args))
            return 7 if name == "store_script" else 0

        return call


def test_two_pwm_channels_drive_four_physical_pins_and_motor_signs_are_independent():
    backend = Pigpio()
    config = replace(calibrated(), motor_signs=(1, -1, -1, 1))
    motors = PiMotors(config, backend, clock=lambda: 0)
    backend.calls.clear()
    motors.apply(60, 30)
    pwm = {args[0]: args[2] for method, args in backend.calls if method == "hardware_PWM"}
    assert pwm[12] == pwm[18] == round(30 * 1000000 / 255)
    assert pwm[13] == pwm[19] == round(60 * 1000000 / 255)
    writes = {args[0]: args[1] for method, args in backend.calls if method == "write"}
    assert (writes[4], writes[3], writes[27], writes[22]) == (1, 0, 0, 1)
    assert (writes[5], writes[23], writes[9], writes[11]) == (0, 1, 1, 0)
    assert writes[17] == writes[6] == 1
    motors.close()
    assert backend.stopped
    assert ("delete_script", (7,)) in backend.calls


def test_unavailable_daemon_preserves_connection_error_and_closes_client():
    backend = Pigpio()
    backend.connected = False
    with pytest.raises(OSError, match="Local pigpiod is unavailable"):
        PiMotors(calibrated(), backend)
    assert backend.stopped
    assert backend.calls == []


@pytest.mark.parametrize("failure", ["watchdog", "host_clock", "pwm_limit"])
def test_pwm_watchdog_failure_never_reenables_standby(failure):
    backend = Pigpio()
    clock = [0]
    motors = PiMotors(calibrated(), backend, clock=lambda: clock[0])
    motors.apply(50, 50)
    backend.calls.clear()
    pwm = 50
    if failure == "watchdog":
        backend.parameters[9] = 1
    elif failure == "host_clock":
        clock[0] = 0.3
    else:
        pwm = 101
    with pytest.raises((ValueError, OSError)):
        motors.apply(pwm, pwm)
    assert not any(name == "write" and args[0] in (17, 6) and args[1] for name, args in backend.calls)
    assert motors.last_output == (0, 0)
    motors.close()


@pytest.mark.parametrize(
    "fields",
    [
        {"right_direction_pins": (5, 23, 13, 11)},
        {"left_pwm_pins": (12, 13)},
        {"right_direction_pins": (5, 0, 9, 11)},
        {"right_direction_pins": (5, 14, 9, 11)},
        {"motor_signs": (True, 1, 1, 1)},
        {"pwm_frequency": 100001},
        {"ir_active_low": 1},
    ],
)
def test_gpio_conflicts_reserved_pins_and_invalid_parameters_are_rejected(fields):
    with pytest.raises(ValueError):
        replace(calibrated(), **fields)
