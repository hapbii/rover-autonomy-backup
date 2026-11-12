"""Verify all snapshot bytes, optionally restoring original relative paths."""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path, PurePosixPath


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1048576), b""):
            result.update(block)
    return result.hexdigest()


def safe(root, relative):
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts:
        raise ValueError("Unsafe manifest path")
    result = root.joinpath(*value.parts)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError("Manifest path escapes the selected directory")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--restore-to", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / "BACKUP_MANIFEST.json").read_text(encoding="utf-8"))
    destination = args.restore_to.resolve() if args.restore_to else None
    if destination and destination.exists():
        raise ValueError("Restore destination must be new; existing files are never overwritten")
    for index, record in enumerate(manifest["files"], 1):
        path = safe(root, record["path"])
        if path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
            raise ValueError(f"Backup hash mismatch: {record['path']}")
        if index % 1000 == 0:
            print(f"Verified {index} files", flush=True)
    if destination:
        destination.mkdir(parents=True)
        for record in manifest.get("directories", []):
            safe(destination, record["restore_path"]).mkdir(parents=True, exist_ok=True)
        for record in manifest["files"]:
            source = safe(root, record["path"])
            target = safe(destination, record["restore_path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            os.utime(target, ns=(record["mtime_ns"], record["mtime_ns"]))
            if digest(target) != record["sha256"]:
                raise ValueError(f"Restored content mismatch: {record['restore_path']}")
        for record in reversed(manifest.get("directories", [])):
            os.utime(safe(destination, record["restore_path"]), ns=(record["mtime_ns"], record["mtime_ns"]))
    print(json.dumps({"verified_files": len(manifest["files"]), "verified_bytes": manifest["total_bytes"],
                      "sha256_passed": True, "restored_to": str(destination) if destination else None,
                      "pi_original_snapshot_included": manifest["pi_original_snapshot_included"]}, indent=2))


if __name__ == "__main__":
    main()
