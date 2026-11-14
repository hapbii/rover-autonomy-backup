"""RA2 sensor-only Uno protocol over GPIO UART (or an explicitly selected USB port)."""

from dataclasses import dataclass

from rover_autonomy.config import HardwareConfig

READY = "RA2 READY ENC_2_4_6_7_A3_A4_A2_A5 US_A0_A1 IR_8_9_10_11_12"


def signed_sequence_delta(value: int, previous: int) -> int:
    return ((value - previous + 2**31) % 2**32) - 2**31


@dataclass(frozen=True, slots=True)
class SensorTelemetry:
    sequence: int
    sample_us: int
    counts: tuple[int, int, int, int]  # LF RF LR RR
    range_mm: int
    flags: int  # bit 2: valid, recent ultrasonic reading
    ir_mask: int  # raw HIGH bits, left to right

    def ir_values(self, active_low=True):
        return tuple(int(bool(self.ir_mask & (1 << bit)) != active_low) for bit in range(5))


def parse_telemetry(line: str) -> SensorTelemetry:
    fields = line.split()
    if len(fields) != 10 or fields[0] != "S":
        raise ValueError("Invalid RA2 telemetry field count")
    sequence, stamp, *values = map(int, fields[1:])
    counts = tuple(values[:4])
    distance, flags, ir_mask = values[4:]
    if any(not 0 <= value < 2**32 for value in (sequence, stamp, *counts)):
        raise ValueError("Sensor timestamp/sequence/count outside uint32")
    if not -1 <= distance <= 4000 or flags not in (0, 4) or not 0 <= ir_mask <= 31:
        raise ValueError("Sensor telemetry bounds exceeded")
    if (flags == 4 and distance < 20) or (flags == 0 and distance != -1):
        raise ValueError("Inconsistent ultrasonic validity")
    return SensorTelemetry(sequence, stamp, counts, distance, flags, ir_mask)


class SensorLink:
    def __init__(self, port, config: HardwareConfig, now: float, transport=None):
        # Encoder probe/bench use the sensor link without measured vehicle geometry.
        if transport is None:
            import serial

            options = dict(port=port, baudrate=config.baud, timeout=0, write_timeout=0.05)
            if str(port).startswith("/"):
                options["exclusive"] = True
            transport = serial.Serial(**options)
        self.transport = transport
        self.config = config
        self.state = "boot"
        self.connected_at = now
        self.last_hello = -100.0
        self.last_feedback = now
        self.buffer = bytearray()
        self.latest = None
        self.fault = ""
        self.closed = False

    def send(self, message):
        data = (message + "\n").encode("ascii")
        if self.transport.write(data) != len(data):
            raise OSError("Partial serial write")

    def _receive(self, line, now):
        if line.startswith(("RA1", "EM2")):
            raise ValueError("Old motor firmware detected: upload RA2 sensor firmware")
        if line.startswith("RA2 READY"):
            if self.state != "hello" or line != READY:
                raise ValueError("Firmware/wiring mismatch or unexpected restart")
            self.send("CFG " + " ".join(map(str, self.config.encoder_signs)))
            self.state = "configuring"
            self.connected_at = now
        elif line == "RA2 CONFIGURED" and self.state == "configuring":
            self.state = "configured"
            self.last_feedback = now
        elif line == "RA2 BOOT" and self.state not in ("boot", "hello"):
            raise ValueError("Uno restarted; explicit disarm/reconnect required")
        elif line.startswith("RA2 ERROR"):
            raise ValueError(line)
        elif line.startswith("S "):
            value = parse_telemetry(line)
            if self.state != "configured":
                return
            if self.latest is not None:
                if signed_sequence_delta(value.sequence, self.latest.sequence) <= 0:
                    return
                if signed_sequence_delta(value.sample_us, self.latest.sample_us) <= 0:
                    raise ValueError("Sensor clock stopped/restarted")
            self.latest = value
            self.last_feedback = now
        elif line and line != "RA2 BOOT":
            raise ValueError("Unexpected sensor protocol message")

    def tick(self, now):
        if self.closed or self.state == "fault":
            return
        try:
            self.buffer.extend(self.transport.read(1024))
            while b"\n" in self.buffer:
                raw, _, remaining = self.buffer.partition(b"\n")
                self.buffer = bytearray(remaining)
                if len(raw) > 200:
                    raise ValueError("Sensor line too long")
                self._receive(raw.decode("ascii", errors="strict").strip(), now)
            if len(self.buffer) > 200:
                raise ValueError("Sensor buffer limit")
            if self.state == "boot" and now - self.connected_at >= 2:
                self.state = "hello"
            if self.state == "hello":
                if now - self.connected_at > 8:
                    raise ValueError("RA2 handshake timeout")
                if now - self.last_hello >= 0.5:
                    self.send("HELLO")
                    self.last_hello = now
            elif self.state == "configuring" and now - self.connected_at > 2:
                raise ValueError("Sensor configuration acknowledgement timeout")
            elif self.state == "configured" and now - self.last_feedback > 0.35:
                raise ValueError("Sensor telemetry timeout")
        except (OSError, UnicodeError, ValueError) as error:
            self.fault = str(error)
            self.state = "fault"

    def close(self):
        if self.closed:
            return
        transport, self.transport = self.transport, None
        self.closed = True
        self.state = "closed"
        self.latest = None
        self.buffer.clear()
        transport.close()
