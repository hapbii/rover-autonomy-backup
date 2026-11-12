"""Compile the RA1 Uno firmware and save the compiler's memory-size report."""

import os
import subprocess
import sys
from pathlib import Path

from setup_arduino import ROOT, arduino_environment


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    output = ROOT / "artifacts/firmware"
    output.mkdir(parents=True, exist_ok=True)
    binary = ROOT / "tools/arduino-cli.exe" if os.name == "nt" else Path("arduino-cli")
    command = [
        str(binary),
        "compile",
        "--fqbn",
        "arduino:avr:uno",
        "--warnings",
        "all",
        "--output-dir",
        str(output),
        str(ROOT / "firmware/rover_camera"),
    ]
    result = subprocess.run(
        command, text=True, encoding="utf-8", errors="replace", capture_output=True, env=arduino_environment()
    )
    text = result.stdout + result.stderr
    (output / "build_report.txt").write_text(text, encoding="utf-8")
    print(text)
    result.check_returncode()


if __name__ == "__main__":
    main()
