import glob
import hashlib
import json
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

home = Path.home().resolve()
workspace = home / "robot_ws"
record = json.loads((workspace / "artifacts/deployment_cleanup.json").read_text())
proof = json.loads((home / "rover_latest_verified_backup.json").read_text())
backup = Path(proof["backup"])
manifest = json.loads(Path(str(backup) + ".manifest.json").read_text())
for relative, value in manifest.items():
    path = backup / relative
    if value["type"] == "file" and hashlib.sha256(path.read_bytes()).hexdigest() != value["sha256"]:
        raise RuntimeError("Final backup content check failed")
    if value["type"] == "symlink" and os.readlink(path) != value["target"]:
        raise RuntimeError("Final backup link check failed")
stage = Path(record["staging"])
if stage.exists():
    if stage.is_symlink() or stage.parent != home or not stage.name.startswith(".rover_stage_"):
        raise RuntimeError("Unexpected stage path")
    shutil.rmtree(stage)
cache_removed = []
for folder, dirs, _ in os.walk(workspace, followlinks=False):
    dirs[:] = [name for name in dirs if name not in (".venv", ".git", "build", "install")]
    for name in list(dirs):
        if name not in ("__pycache__", ".pytest_cache", ".ruff_cache"):
            continue
        path = Path(folder) / name
        if path.is_symlink() or not path.resolve().is_relative_to(workspace):
            raise RuntimeError("Unexpected cache path")
        shutil.rmtree(path)
        dirs.remove(name)
        cache_removed.append(str(path.relative_to(workspace)))
tests = ET.parse(workspace / "artifacts/pi_test_report.xml").getroot()
suites = list(tests) if tests.tag != "testsuite" else [tests]
results = {key: sum(int(item.attrib.get(key, 0)) for item in suites)
           for key in ("tests", "failures", "errors", "skipped")}
sim = json.loads((workspace / "artifacts/pi_ros_simulation_report.json").read_text())
image = json.loads((workspace / "artifacts/pi_ros_image_report.json").read_text())
report = {
    "at": datetime.now(timezone.utc).isoformat(), "host": "takyeji@192.168.50.34",
    "workspace": str(workspace), "backup": proof, "backup_rechecked": True,
    "removed_paths": record["removed_paths"], "preserved": record["preserved"],
    "staging_removed": str(stage), "cache_removed": cache_removed,
    "build": "passed", "unit_tests": results,
    "ros_smoke_simulation": sim, "ros_smoke_reference_image": image,
    "usb_devices": subprocess.run(["lsusb"], capture_output=True, text=True).stdout.splitlines(),
    "serial_devices": glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"),
    "camera_model": "OV5647", "physical_camera_capture": "failed",
    "camera_errors": ["ROS libcamera 0.7.2 IPA: V4L2 controls require ControlInfoMap",
                      "System libcamera 0.2.0 cam capture: prepareIsp buffers_.end assertion"],
    "native_camera_failure_is_below_python_pipeline": True,
    "diagnostic_libcamera_v4l2_package": "tested then removed; not deployed as workaround",
    "firmware_uploaded": False, "hardware_motor_commands_sent": False,
    "hardware_enabled": False, "calibrated": False,
    "canonical_environment": "source ~/robot_ws/env.sh",
    "pending": ["Uno USB enumeration", "Native camera stack capture repair",
                "Confirm encoder/sonar wiring", "Measured wheel/CPR/sign calibration",
                "RA1 firmware upload and low-output bench test"],
    "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
    "uptime_seconds": float(Path("/proc/uptime").read_text().split()[0]),
}
destination = workspace / "artifacts/pi_deployment_report.json"
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
