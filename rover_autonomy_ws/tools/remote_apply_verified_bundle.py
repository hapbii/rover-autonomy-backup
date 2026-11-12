import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

home = Path.home().resolve()
workspace = home / "robot_ws"
if workspace.is_symlink() or workspace.resolve() != workspace:
    raise RuntimeError("Unexpected active workspace")
archive_path = home / "rover_autonomy_pi_bundle.zip"
digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
if digest != sys.argv[1]:
    raise RuntimeError("Final archive SHA-256 mismatch")
copied = []
with tempfile.TemporaryDirectory(prefix=".rover_update_", dir=home) as temporary:
    stage = Path(temporary)
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != "rover_autonomy_ws":
                raise RuntimeError("Invalid archive path")
        archive.extractall(stage)
    source = stage / "rover_autonomy_ws"
    manifest = json.loads((source / "TRANSFER_MANIFEST.json").read_text())
    for relative, expected in manifest.items():
        if hashlib.sha256((source / relative).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Archive manifest mismatch: {relative}")
        if relative.startswith("artifacts/"):
            continue  # Keep the Pi's own runtime evidence; source sync is separate.
        target = workspace / relative
        if target.is_symlink() or not target.resolve().is_relative_to(workspace):
            raise RuntimeError(f"Unexpected deployment link/path: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Copied source verification failed: {relative}")
        copied.append(relative)
    shutil.copy2(source / "TRANSFER_MANIFEST.json", workspace / "TRANSFER_MANIFEST.json")
(workspace / "scripts/build.sh").chmod(0o755)
report = {"at": datetime.now(timezone.utc).isoformat(), "workspace": str(workspace),
          "bundle_sha256": digest, "source_files_verified": len(copied),
          "source_paths": copied, "runtime_evidence_preserved": True,
          "firmware_uploaded": False, "hardware_enabled": False}
(workspace / "artifacts/deployment_source_sync.json").write_text(json.dumps(report, indent=2))
print(json.dumps({key: value for key, value in report.items() if key != "source_paths"}, indent=2))
