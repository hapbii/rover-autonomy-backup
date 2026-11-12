"""RA1 serial link with explicit configuration, bounded buffers and restart interlock."""

from dataclasses import dataclass
from math import isfinite

from rover_autonomy.config import HardwareConfig

READY = "RA1 READY CAMERA_US 3 5 9 8 11 12 10"


@dataclass(frozen=True, slots=True)
class Telemetry:
    sequence: int
    counts: tuple[int, int, int, int]
    right_rpm: float
    left_rpm: float
    right_pwm: int
    left_pwm: int
    range_mm: int
    flags: int


def parse_telemetry(line: str) -> Telemetry:
    values = line.split()
    if len(values) != 12 or values[0] != "T":
        raise ValueError("Invalid telemetry field count")
    sequence = int(values[1])
    counts = tuple(int(value) for value in values[2:6])
    rpm_r, rpm_l = float(values[6]), float(values[7])
    pwm_r, pwm_l, range_mm, flags = map(int, values[8:12])
    if not 0 <= sequence < 2**32 or any(not 0 <= value < 2**32 for value in counts):
        raise ValueError("Telemetry sequence/count outside uint32")
    if not all(isfinite(value) and abs(value) <= 2000 for value in (rpm_r, rpm_l)):
        raise ValueError("Invalid measured RPM")
    if max(abs(pwm_r), abs(pwm_l)) > 100 or not -1 <= range_mm <= 4000 or not 0 <= flags <= 7:
        raise ValueError("Telemetry bounds exceeded")
    return Telemetry(sequence, counts, rpm_r, rpm_l, pwm_r, pwm_l, range_mm, flags)


class SerialLink:
    def __init__(self, port, config: HardwareConfig, now: float, transport=None):
        config.validate_for_motion()
        self.config = config
        if transport is None:
            import serial

            options = dict(port=port, baudrate=config.baud, timeout=0, write_timeout=0.05)
            if str(port).startswith("/"):
                options["exclusive"] = True
            transport = serial.Serial(**options)
        self.transport = transport
        self.state = "boot"
        self.connected_at = now
        self.last_hello = -100.0
        self.last_feedback = now
        self.last_write = -100.0
        self.buffer = bytearray()
        self.latest: Telemetry | None = None
        self.last_sequence: int | None = None
        self.arm_requested = False
        self.saw_disarmed = False
        self.fault = ""
        self.closed = False

    def send(self, message: str):
        data = (message + "\n").encode("ascii")
        if self.transport.write(data) != len(data):
            raise OSError("Partial serial write")

    def set_arm(self, armed: bool):
        if not armed:
            self.arm_requested = False
            self.saw_disarmed = True
            if self.state in ("armed", "arming"):
                try:
                    self.send("STOP")
                    self.state = "configured"
                except (OSError, ValueError) as error:
                    self._fail(str(error))
        elif self.saw_disarmed:
            self.arm_requested = True

    def _fail(self, reason):
        self.fault = reason
        self.state = "fault"
        self.arm_requested = False
        self.saw_disarmed = False
        try:
            self.send("STOP")
        except (OSError, ValueError):
            pass

    def _receive(self, line: str, now: float):
        if line.startswith("RA1 READY"):
            if self.state != "hello":
                self._fail("Unexpected firmware restart; explicit disarm/reconnect required")
                return
            if line != READY:
                self._fail("Firmware/wiring mismatch")
                return
            cfg = self.config
            signs = " ".join(str(value) for value in cfg.encoder_signs)
            self.send(
                f"CFG {cfg.encoder_ticks_per_rev} {cfg.pid_kp} {cfg.pid_ki} {cfg.pid_kd} {cfg.feedforward} {cfg.max_pwm} {signs}"
            )
            self.state = "configuring"
            self.connected_at = now
        elif line == "RA1 CONFIGURED" and self.state == "configuring":
            self.state = "configured"
            self.last_feedback = now
        elif line == "RA1 ARMED" and self.state == "arming":
            self.state = "armed"
            self.last_feedback = now
        elif line == "RA1 STOPPED" and self.state in ("armed", "arming"):
            self.state = "configured"
            self.arm_requested = False
            self.saw_disarmed = False
        elif line.startswith("RA1 FAULT") or line == "RA1 TIMEOUT":
            self._fail(line)
        elif line == "RA1 BOOT" and self.state not in ("boot", "hello"):
            self._fail("Board restarted; disarm/reconnect required")
        elif line.startswith("T "):
            value = parse_telemetry(line)
            if (
                self.last_sequence is not None
                and signed_sequence_delta(value.sequence, self.last_sequence) <= 0
            ):
                return
            self.last_sequence = value.sequence
            self.latest = value
            self.last_feedback = now
            if value.flags & 2:
                self._fail("Firmware encoder/stall fault")

    def tick(self, now: float, right_rpm: float = 0.0, left_rpm: float = 0.0):
        if self.closed or self.state == "fault":
            return
        try:
            self.buffer.extend(self.transport.read(1024))
            while b"\n" in self.buffer:
                raw, _, remainder = self.buffer.partition(b"\n")
                self.buffer = bytearray(remainder)
                if len(raw) > 200:
                    raise ValueError("Serial line too long")
                self._receive(raw.decode("ascii", errors="strict").strip(), now)
                if self.state == "fault":
                    return
            if len(self.buffer) > 200:
                raise ValueError("Serial buffer limit")
            if self.state == "boot":
                if now - self.connected_at < 2.0:
                    return
                self.state = "hello"
            if self.state == "hello":
                if now - self.connected_at > 8:
                    self._fail("RA1 handshake timeout")
                elif now - self.last_hello > 0.5:
                    self.send("HELLO")
                    self.last_hello = now
            elif self.state in ("configuring", "arming"):
                if now - self.connected_at > 2:
                    self._fail("Configuration/arm acknowledgement timeout")
            elif self.state == "configured" and self.arm_requested and self.saw_disarmed:
                if now - self.last_feedback > 0.35:
                    self._fail("Fresh telemetry is required before arming")
                    return
                self.send("ARM")
                self.state = "arming"
                self.connected_at = now
            elif self.state == "armed":
                if not self.arm_requested:
                    self.send("STOP")
                    self.state = "configured"
                    return
                if now - self.last_feedback > 0.35:
                    self._fail("Telemetry timeout")
                    return
                if not all(
                    isfinite(value) and abs(value) <= self.config.max_rpm for value in (right_rpm, left_rpm)
                ):
                    self._fail("Invalid target RPM")
                    return
                if now - self.last_write >= 0.045:
                    self.send(f"V {right_rpm:.3f} {left_rpm:.3f}")
                    self.last_write = now
            elif self.state == "configured" and now - self.last_feedback > 0.5:
                self._fail("Telemetry stopped while disarmed")
        except (OSError, UnicodeError, ValueError) as error:
            self._fail(str(error))

    def close(self):
        if self.closed:
            return
        try:
            self.send("STOP")
        except (OSError, ValueError):
            pass
        finally:
            transport, self.transport = self.transport, None
            self.closed = True
            self.state = "closed"
            self.arm_requested = self.saw_disarmed = False
            self.buffer.clear()
            self.latest = None
            transport.close()


def signed_sequence_delta(value: int, previous: int) -> int:
    return ((value - previous + 2**31) % 2**32) - 2**31
