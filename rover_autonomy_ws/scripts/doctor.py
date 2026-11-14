"""Read-only environment/configuration report; never opens camera or serial."""

import argparse
import importlib.util
import json
import platform
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/rover_autonomy"))
from rover_autonomy.config import HardwareConfig, load_configuration


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-ros", action="store_true")
    parser.add_argument("--config", type=Path, default=ROOT / "src/rover_autonomy/config/rover.yaml")
    args = parser.parse_args()
    config = load_configuration(args.config)
    hardware = HardwareConfig(**config.get("hardware", {}))
    ros_available = importlib.util.find_spec("rclpy") is not None
    try:
        hardware.validate_for_motion()
        live_ready, reason = True, "configuration calibrated; physical verification still required"
    except ValueError as error:
        live_ready, reason = False, str(error)
    report = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "numpy": np.__version__,
        "ros_rclpy_available": ros_available,
        "picamera2_available": importlib.util.find_spec("picamera2") is not None,
        "pigpio_client_available": importlib.util.find_spec("pigpio") is not None,
        "motor_backend": "Pi 4 pigpiod hardware PWM0 left=12/18, PWM1 right=13/19",
        "sensor_firmware": "RA2 rover_sensors; Uno has no motor output",
        "configuration_valid": True,
        "live_output_configured": live_ready,
        "live_output_note": reason,
        "default_sign_backend": config.get("perception", {}).get("sign_backend", "geometry"),
        "real_sign_photo_validation": "not performed; no project dataset supplied",
        "models": [
            path.name for path in sorted((ROOT / "src/rover_autonomy/models").glob("*")) if path.is_file()
        ],
        "camera_or_serial_opened": False,
    }
    out = ROOT / "artifacts/environment_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if args.require_ros and not ros_available else 0


if __name__ == "__main__":
    raise SystemExit(main())
