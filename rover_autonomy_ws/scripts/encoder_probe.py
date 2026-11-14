"""Read RA2 sensor counts/sonar/IR by hand. Never opens Pi motor GPIO."""

import argparse
import sys
import time
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/rover_autonomy"))
from rover_autonomy.hardware.kinematics import signed_count_delta
from rover_autonomy.hardware.protocol import READY, parse_telemetry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--duration", type=float, default=20)
    args = parser.parse_args()
    if not 1 <= args.duration <= 300:
        parser.error("duration must be between 1 and 300 seconds")
    identified = False
    buffer = bytearray()
    baseline = None
    with serial.Serial(args.port, 115200, timeout=0.05, write_timeout=0.1) as connection:
        try:
            time.sleep(2)
            connection.write(b"HELLO\n")
            deadline = time.monotonic() + args.duration
            last_display = 0.0
            while time.monotonic() < deadline:
                buffer.extend(connection.read(512))
                if len(buffer) > 2048:
                    raise ValueError("Unexpected/unbounded serial input")
                while b"\n" in buffer:
                    raw, _, remaining = buffer.partition(b"\n")
                    buffer = bytearray(remaining)
                    text = raw.decode("ascii", errors="replace").strip()
                    if text == READY:
                        identified = True
                        connection.write(b"CFG 1 1 1 1\n")
                        print(
                            "RA2 identified. Turn one shaft by hand; LF RF LR RR. IR order left->right.",
                            flush=True,
                        )
                    elif text.startswith(("EM2 ", "RA1 ")):
                        raise RuntimeError("Old motor firmware detected; upload RA2 before sensor wiring")
                    elif identified and text.startswith("S "):
                        value = parse_telemetry(text)
                        if baseline is None:
                            baseline = value.counts
                        if time.monotonic() - last_display > 0.25:
                            delta = [
                                signed_count_delta(current, old)
                                for current, old in zip(value.counts, baseline, strict=True)
                            ]
                            print(
                                "counts since start:",
                                *delta,
                                "sonar_mm:",
                                value.range_mm,
                                "IR raw:",
                                value.ir_mask,
                                "IR active-low:",
                                value.ir_values(),
                                flush=True,
                            )
                            last_display = time.monotonic()
            if not identified:
                raise RuntimeError("Matching RA2 firmware not detected")
        finally:
            # Sensor-only firmware has no motor output or ARM command to release.
            pass


if __name__ == "__main__":
    main()
