"""Full current workspace backup, including inactive lgpio FIFO metadata."""
import hashlib
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path

home = Path.home().resolve()
source = home / "robot_ws"
if source.is_symlink() or source.resolve() != source or not source.is_dir():
    raise RuntimeError("Unexpected workspace path")


def manifest(root):
    records = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in sorted(dirs + files):
            path = Path(folder) / name
            info = path.lstat()
            entry = {"mode": stat.S_IMODE(info.st_mode)}
            if path.is_symlink():
                entry.update(type="link", target=os.readlink(path))
            elif path.is_dir():
                entry.update(type="directory")
            elif stat.S_ISFIFO(info.st_mode):
                entry.update(type="fifo")
            elif stat.S_ISREG(info.st_mode):
                entry.update(type="file", bytes=info.st_size,
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            else:
                raise RuntimeError(f"Unrecognized special file {path}")
            records[str(path.relative_to(root))] = entry
    return records


before = manifest(source)
size = sum(entry.get("bytes", 0) for entry in before.values())
if shutil.disk_usage(home).free < size * 2 + 100 * 1048576:
    raise RuntimeError("Not enough free space")
destination = home / ("robot_ws_backup_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"))
if destination.exists():
    raise RuntimeError("Backup already exists")


def skip_fifo(folder, names):
    return [name for name in names if stat.S_ISFIFO((Path(folder) / name).lstat().st_mode)]


shutil.copytree(source, destination, symlinks=True, ignore=skip_fifo)
for relative, entry in before.items():
    if entry["type"] == "fifo":
        os.mkfifo(destination / relative, entry["mode"])
        (destination / relative).chmod(entry["mode"])
if manifest(source) != before or manifest(destination) != before:
    raise RuntimeError("Source changed or backup hash/metadata mismatch; do not deploy")
proof = dict(source=str(source), backup=str(destination), verified=True,
             files=sum(entry["type"] == "file" for entry in before.values()),
             file_bytes=size, fifo_metadata_preserved=[p for p, e in before.items() if e["type"] == "fifo"],
             verified_at=datetime.now(timezone.utc).isoformat())
Path(str(destination) + ".manifest.json").write_text(json.dumps(before, indent=2))
Path(str(destination) + ".verification.json").write_text(json.dumps(proof, indent=2))
(home / "rover_latest_verified_backup.json").write_text(json.dumps(proof, indent=2))
print(json.dumps(proof, indent=2), flush=True)
