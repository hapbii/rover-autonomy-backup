import json
import os
import time
from importlib.metadata import version
from pathlib import Path

import cv2
import libcamera
import numpy as np

from rover_autonomy.hardware.camera import PiCamera

print("libcamera_binding", libcamera.__file__, flush=True)
print("picamera2", version("picamera2"), flush=True)
environment = {key: value for key, value in os.environ.items()
               if key in ("PYTHONPATH", "LD_LIBRARY_PATH") or key.startswith("LIBCAMERA_")}
camera = PiCamera(640, 480, 12)
try:
    start = time.monotonic()
    for count in range(30):
        image = camera.read()
        assert image.shape == (480, 640, 3) and image.dtype == np.uint8
    elapsed = time.monotonic() - start
    destination = Path.home() / "robot_ws/artifacts/pi_camera_preview.jpg"
    assert cv2.imwrite(str(destination), image)
    report = {"passed": True, "frames": 30, "shape": list(image.shape), "elapsed_seconds": elapsed,
              "fps": 30 / elapsed, "mean": float(image.mean()), "std": float(image.std()),
              "preview": str(destination), "environment": environment,
              "libcamera_binding": str(libcamera.__file__), "picamera2": version("picamera2"),
              "hardware_motor_output": False}
    (destination.parent / "pi_camera_patch_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)
finally:
    camera.close()
