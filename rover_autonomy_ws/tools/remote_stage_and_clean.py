import hashlib
import json
import os
import shutil
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

home = Path.home().resolve()
workspace = home / "robot_ws"
proof = json.loads((home / "rover_latest_verified_backup.json").read_text())
backup = Path(proof["backup"])
if not proof["verified"] or workspace.is_symlink() or workspace.resolve() != workspace:
    raise RuntimeError("Backup or workspace guard failed")
if backup.parent != home or not backup.name.startswith("robot_ws_backup_") or backup.is_symlink():
    raise RuntimeError("Unexpected backup location")
original_manifest = json.loads(Path(str(backup) + ".manifest.json").read_text())


def inspect(root):
    result = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(folder) / name
            info = path.lstat()
            key = str(path.relative_to(root))
            if path.is_symlink():
                result[key] = {"type": "symlink", "target": os.readlink(path)}
            elif path.is_dir():
                result[key] = {"type": "directory", "mode": stat.S_IMODE(info.st_mode)}
            elif stat.S_ISREG(info.st_mode):
                result[key] = {"type": "file", "bytes": info.st_size, "mode": stat.S_IMODE(info.st_mode),
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            else:
                raise RuntimeError(f"Unexpected special file: {path}")
    return result


if inspect(backup) != original_manifest or inspect(workspace) != original_manifest:
    raise RuntimeError("Workspace changed since backup or backup is incomplete; cleanup prohibited")
archive_path = home / "rover_autonomy_pi_bundle.zip"
expected = "7ea46fe17513afb45f1ed85727f4bc2d45747a978e4e1aa3fe2bc70b33702e33"
actual = hashlib.sha256(archive_path.read_bytes()).hexdigest()
if actual != expected:
    raise RuntimeError("Deployment ZIP SHA-256 mismatch")
staging = home / (".rover_stage_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
staging.mkdir(exist_ok=False)
with zipfile.ZipFile(archive_path) as archive:
    for name in archive.namelist():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.parts[0] != "rover_autonomy_ws":
            raise RuntimeError("Unexpected archive member")
    if archive.testzip() is not None:
        raise RuntimeError("Corrupt ZIP")
    archive.extractall(staging)
new_source = staging / "rover_autonomy_ws"
manifest = json.loads((new_source / "TRANSFER_MANIFEST.json").read_text())
for relative, digest in manifest.items():
    if hashlib.sha256((new_source / relative).read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"Source manifest mismatch: {relative}")

obsolete = ["build", "install", "log", "src/robot_base", "src/robot_mission", "src/robot_bringup",
            "src/encoder_motor", "firmware/two_motor_test", "firmware/two_motor_test_stby13",
            "firmware/three_ir_four_encoder", "firmware/robot_arduino", "scripts/setup_pi.sh"]
deleted = []
for relative in obsolete:
    path = workspace / relative
    if not path.exists() and not path.is_symlink():
        continue
    resolved = path.resolve()
    if not resolved.is_relative_to(workspace) or resolved == workspace:
        raise RuntimeError(f"Unsafe cleanup path: {path}")
    deleted.append(relative)
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)
for path in new_source.iterdir():
    target = workspace / path.name
    if path.is_dir():
        shutil.copytree(path, target, dirs_exist_ok=True)
    else:
        shutil.copy2(path, target)
for relative, digest in manifest.items():
    if hashlib.sha256((workspace / relative).read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"Deployed source verification failed: {relative}")
(workspace / "env.sh").write_text('''# Source this file from any terminal.
_ROVER_WS="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
source /opt/ros/jazzy/setup.bash
[ ! -f "$_ROVER_WS/.venv/bin/activate" ] || source "$_ROVER_WS/.venv/bin/activate"
[ ! -f "$_ROVER_WS/install/setup.bash" ] || source "$_ROVER_WS/install/setup.bash"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-9}"
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
unset _ROVER_WS
''')
(workspace / "scripts/build.sh").write_text('''#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
source ./env.sh
.venv/bin/python "$(command -v colcon)" build --symlink-install --packages-select rover_autonomy "$@"
''')
(workspace / "scripts/build.sh").chmod(0o755)
report = {"workspace": str(workspace), "backup": str(backup), "backup_verified": True,
          "bundle_sha256": actual, "source_manifest_files_verified": len(manifest),
          "removed_paths": deleted, "preserved": [".git", "firmware/backups"],
          "staging": str(staging), "hardware_enabled": False, "firmware_uploaded": False,
          "at": datetime.now(timezone.utc).isoformat()}
(workspace / "artifacts/deployment_cleanup.json").write_text(json.dumps(report, indent=2))
(home / "rover_latest_deployment.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2), flush=True)
