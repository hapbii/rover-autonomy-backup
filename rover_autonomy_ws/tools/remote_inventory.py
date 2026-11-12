import glob
import importlib.util
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

home = Path.home()
workspace = home / "robot_ws"


def command(args, timeout=15):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"exit": result.returncode, "stdout": result.stdout[:14000], "stderr": result.stderr[:3000]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"error": str(error)}


report = {
    "host": platform.node(), "platform": platform.platform(), "python": platform.python_version(),
    "home": str(home), "workspace_exists": workspace.exists(),
    "workspace_resolved": str(workspace.resolve()), "workspace_is_symlink": workspace.is_symlink(),
    "disk": dict(zip(("total", "used", "free"), shutil.disk_usage(home))),
    "ros_installations": glob.glob("/opt/ros/*"),
    "devices": sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*") + glob.glob("/dev/video*")),
    "modules_without_ros_overlay": {name: importlib.util.find_spec(name) is not None
                                    for name in ("cv2", "numpy", "yaml", "serial", "picamera2", "libcamera")},
    "top_level": [], "workspace_files": [], "workspace_links": [], "instructions": {},
}
for path in (home / "AGENTS.md", workspace / "AGENTS.md"):
    if path.is_file():
        report["instructions"][str(path)] = path.read_text()[:30000]
if workspace.is_dir():
    report["size"] = command(["du", "-sh", str(workspace)])
    for path in sorted(workspace.iterdir()):
        report["top_level"].append({"name": path.name, "directory": path.is_dir(), "symlink": path.is_symlink()})
    for directory, names, files in os.walk(workspace, followlinks=False):
        folder = Path(directory)
        for name in names + files:
            path = folder / name
            if path.is_symlink():
                report["workspace_links"].append({"path": str(path.relative_to(workspace)), "target": os.readlink(path)})
        names[:] = [name for name in names if name not in ("build", "install", "log", ".venv", "__pycache__", ".git")]
        for name in files:
            path = folder / name
            if name == "AGENTS.md":
                report["instructions"][str(path)] = path.read_text()[:30000]
            if len(report["workspace_files"]) < 220:
                report["workspace_files"].append(str(path.relative_to(workspace)))
processes = command(["ps", "-eo", "pid,ppid,user,comm,args"])
report["relevant_processes"] = [line for line in processes.get("stdout", "").splitlines()
    if any(word in line.lower() for word in ("ros2", "encoder_motor", "two_motor", "rover", "arduino", "camera", "serial"))]
report["usb"] = command(["lsusb"])
report["port_users"] = command(["fuser", "/dev/ttyACM0"])
report["user_services"] = command(["systemctl", "--user", "list-units", "--all", "--no-pager"])
report["ros_environment"] = command(["bash", "-c", "source /opt/ros/jazzy/setup.bash && python3 -c 'import rclpy; print(rclpy.__file__)' && command -v colcon"])
report["shell_workspace_sources"] = [line.strip() for line in (home / ".bashrc").read_text().splitlines()
                                     if "robot_ws" in line or "rover_autonomy_ws" in line or "/opt/ros" in line]
report["arduino_cli"] = command([str(home / ".local/bin/arduino-cli"), "version"])
destination = home / "rover_deployment_inventory.json"
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
