import hashlib
import json
import os
import shutil
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

home = Path.home().resolve()
source = home / "robot_ws"
if source.is_symlink() or source.resolve() != source or not source.is_dir():
    raise RuntimeError("Unexpected workspace path; refusing automatic backup/cleanup")
stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
destination = home / f"robot_ws_backup_{stamp}"
if destination.exists():
    raise RuntimeError("Backup destination already exists")


def manifest(root):
    records = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(folder) / name
            info = path.lstat()
            relative = str(path.relative_to(root))
            if path.is_symlink():
                records[relative] = {"type": "symlink", "target": os.readlink(path)}
            elif path.is_dir():
                records[relative] = {"type": "directory", "mode": stat.S_IMODE(info.st_mode)}
            elif stat.S_ISREG(info.st_mode):
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1048576), b""):
                        digest.update(block)
                records[relative] = {"type": "file", "bytes": info.st_size,
                                     "mode": stat.S_IMODE(info.st_mode), "sha256": digest.hexdigest()}
            else:
                raise RuntimeError(f"Unexpected special file: {relative}")
    return records


before = manifest(source)
size = sum(item.get("bytes", 0) for item in before.values())
if shutil.disk_usage(home).free < size * 2 + 100 * 1048576:
    raise RuntimeError("Insufficient space to create and verify a full backup")
shutil.copytree(source, destination, symlinks=True, copy_function=shutil.copy2)
after = manifest(source)
copied = manifest(destination)
if before != after or copied != before:
    raise RuntimeError("Backup verification failed or source changed; cleanup is prohibited")
proof = {"source": str(source), "backup": str(destination), "verified": True,
         "entries": len(before), "files": sum(item["type"] == "file" for item in before.values()),
         "file_bytes": size, "verified_at": datetime.now(timezone.utc).isoformat()}
Path(str(destination) + ".manifest.json").write_text(json.dumps(before, indent=2))
Path(str(destination) + ".verification.json").write_text(json.dumps(proof, indent=2))
(home / "rover_latest_verified_backup.json").write_text(json.dumps(proof, indent=2))
print("VERIFIED_BACKUP " + json.dumps(proof), flush=True)
for relative in ("README.md", "env.sh", "scripts/build.sh", "scripts/setup_pi.sh",
                 "src/robot_bringup/config/robot.yaml", "src/encoder_motor/config/motor.yaml",
                 "src/robot_base/robot_base/camera_pub.py", "src/robot_base/robot_base/arduino_bridge.py",
                 "src/robot_mission/robot_mission/line_follower.py"):
    path = source / relative
    if path.is_file():
        print("REVIEW " + relative + "\n" + path.read_text()[:12000], flush=True)
for command in (["git", "-C", str(source), "status", "--short"],
                ["v4l2-ctl", "--list-devices"],
                ["v4l2-ctl", "-d", "/dev/video0", "--list-formats-ext"],
                ["bash", "-c", "command -v cam rpicam-hello libcamera-hello gst-launch-1.0; dpkg -l '*libcamera*' '*picamera*' 2>/dev/null | tail -12"],
                ["systemctl", "--user", "list-units", "--type=service", "--all", "--no-pager"]):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        print("CHECK " + repr(command) + "\n" + result.stdout[:6000] + result.stderr[:1000], flush=True)
    except (OSError, subprocess.TimeoutExpired) as error:
        print("CHECK_ERROR " + str(error), flush=True)
