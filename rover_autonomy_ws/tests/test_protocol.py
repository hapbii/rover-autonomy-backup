from dataclasses import replace

import pytest
from rover_autonomy.hardware.kinematics import WheelOdometry, differential_rpm, signed_count_delta
from rover_autonomy.hardware.protocol import READY, SerialLink

from rover_autonomy.config import HardwareConfig


class FakeSerial:
    def __init__(self):
        self.incoming = bytearray()
        self.commands = []
        self.closed = False

    def inject(self, data):
        self.incoming.extend(data.encode())

    def read(self, size):
        result = self.incoming[:size]
        del self.incoming[:size]
        return bytes(result)

    def write(self, data):
        self.commands.append(data.decode().strip())
        return len(data)

    def close(self):
        self.closed = True


def configured_link():
    cfg = HardwareConfig(
        enabled=True, calibrated=True, wheel_radius_m=0.0325, track_width_m=0.19, encoder_ticks_per_rev=960
    )
    serial = FakeSerial()
    link = SerialLink("fake", cfg, 0, serial)
    link.set_arm(False)
    link.tick(2.1)
    serial.inject(READY + "\n")
    link.tick(2.2)
    serial.inject("RA1 CONFIGURED\nT 0 0 0 0 0 0 0 0 0 1200 4\n")
    link.tick(2.3)
    return link, serial


def test_serial_requires_identification_configuration_and_arm_before_motion():
    link, serial = configured_link()
    assert serial.commands[0] == "HELLO"
    assert serial.commands[1].startswith("CFG 960 ")
    assert not any(command.startswith("V ") for command in serial.commands)
    link.set_arm(True)
    link.tick(2.4, 30, -30)
    serial.inject("RA1 ARMED\nT 1 0 0 0 0 0 0 0 0 1200 5\n")
    link.tick(2.5, 30, -30)
    assert serial.commands[-1] == "V 30.000 -30.000"
    link.close()
    assert serial.closed and serial.commands[-1] == "STOP"


def test_packet_fragmentation_and_encoder_wrap():
    link, serial = configured_link()
    serial.inject("T 1 4294967295 ")
    link.tick(2.4)
    serial.inject("2 3 4 -1.2 2.4 0 0 -1 0\n")
    link.tick(2.5)
    assert link.latest.counts[0] == 2**32 - 1
    assert signed_count_delta(0, 2**32 - 1) == 1
    assert signed_count_delta(2**32 - 1, 0) == -1


def test_duplicate_telemetry_does_not_keep_link_alive():
    link, serial = configured_link()
    link.set_arm(True)
    link.tick(2.4)
    serial.inject("RA1 ARMED\nT 1 0 0 0 0 0 0 0 0 1200 5\n")
    link.tick(2.5)
    serial.inject("T 1 0 0 0 0 0 0 0 0 1200 5\n")
    link.tick(2.9)
    assert link.state == "fault"
    assert serial.commands[-1] == "STOP"
    link.set_arm(True)
    link.tick(3.0, 30, 30)
    assert link.state == "fault"


@pytest.mark.parametrize("bad", ["T 0 1\n", "T 1 0 0 0 0 nan 0 0 0 200 4\n", "X" * 300])
def test_malformed_or_unbounded_serial_input_stops(bad):
    link, serial = configured_link()
    serial.inject(bad)
    link.tick(2.4)
    assert link.state == "fault" and serial.commands[-1] == "STOP"
    assert len(link.buffer) <= 1024


def test_wrong_firmware_never_arms():
    link, serial = configured_link()
    serial.inject("RA1 READY OTHER_PINS\n")
    link.tick(2.4)
    assert link.state == "fault"
    assert "ARM" not in serial.commands


def test_previous_stby13_firmware_is_rejected_before_configuration():
    config = HardwareConfig(
        enabled=True, calibrated=True, wheel_radius_m=0.03, track_width_m=0.2, encoder_ticks_per_rev=960
    )
    serial = FakeSerial()
    link = SerialLink("fake", config, 0, serial)
    link.set_arm(False)
    link.tick(2.1)
    serial.inject("RA1 READY CAMERA_US 3 5 9 8 11 12 13\n")
    link.tick(2.2)
    assert link.state == "fault"
    assert link.fault == "Firmware/wiring mismatch"
    assert not any(command.startswith(("CFG ", "V ")) or command == "ARM" for command in serial.commands)
    link.close()


def test_unexpected_ready_cannot_auto_rearm_after_a_board_restart():
    link, serial = configured_link()
    link.set_arm(True)
    serial.inject(READY + "\n")
    link.tick(2.4)
    assert link.state == "fault"
    assert serial.commands[-1] == "STOP"


def test_disarm_during_arm_acknowledgement_cannot_send_a_queued_nonzero_target():
    link, serial = configured_link()
    link.set_arm(True)
    link.tick(2.4, 40, 40)
    assert link.state == "arming"
    link.set_arm(False)
    serial.inject("RA1 ARMED\nT 1 0 0 0 0 0 0 0 0 1200 5\nRA1 STOPPED\n")
    link.tick(2.5, 40, 40)
    assert link.state == "configured"
    assert not any(command.startswith("V ") for command in serial.commands)
    assert serial.commands[-1] == "STOP"


def test_close_error_still_marks_transport_closed():
    link, serial = configured_link()

    def bad_close():
        raise OSError("close failed")

    serial.close = bad_close
    with pytest.raises(OSError):
        link.close()
    assert link.closed
    link.close()


def test_serial_close_drops_queued_input_feedback_and_transport_ownership():
    link, serial = configured_link()
    serial.inject("T 1 unfinished")
    link.tick(2.4)
    assert link.buffer and link.latest is not None
    link.close()
    assert link.transport is None
    assert link.latest is None and not link.buffer
    assert link.state == "closed" and not link.arm_requested
    assert serial.closed


def test_missing_calibration_never_opens_a_port():
    with pytest.raises(ValueError):
        SerialLink("/dev/does_not_exist", HardwareConfig(enabled=True), 0)


@pytest.mark.parametrize(
    "fields",
    [
        dict(calibrated=False),
        dict(calibrated="false"),
        dict(encoder_ticks_per_rev=0),
        dict(encoder_ticks_per_rev=960.5),
        dict(wheel_radius_m=0),
        dict(max_pwm=255),
        dict(encoder_signs=(1, 1, 1, 0)),
        dict(encoder_signs=(True, 1, 1, 1)),
    ],
)
def test_hardware_validation(fields):
    cfg = HardwareConfig(
        enabled=True, calibrated=True, wheel_radius_m=0.03, track_width_m=0.2, encoder_ticks_per_rev=960
    )
    with pytest.raises(ValueError):
        replace(cfg, **fields).validate_for_motion()


def test_differential_steering_and_saturation_preserve_curvature():
    right, left = differential_rpm(0.1, 0.3, 0.03, 0.2, 60)
    assert right > left > 0
    right, left = differential_rpm(0, 0.5, 0.03, 0.2, 60)
    assert right == pytest.approx(-left)
    a, b = differential_rpm(0.5, 1, 0.03, 0.2, 15)
    assert max(abs(a), abs(b)) <= 15
    assert a / b == pytest.approx(1.5)


def test_wheel_odometry_uses_all_four_encoders():
    odom = WheelOdometry(0.03, 0.2, 1000)
    odom.update((0, 0, 0, 0), 0)
    value = odom.update((100, 100, 100, 100), 1)
    assert value.x == pytest.approx(2 * 3.141592653589793 * 0.03 * 0.1)
    assert value.yaw == 0
