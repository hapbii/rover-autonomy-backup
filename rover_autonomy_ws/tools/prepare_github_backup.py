"""Make a byte-verified, complete local rover backup for a private Git repository.

Intentionally includes virtual environments, caches, archived experiments, binary
tools and reports. This is a disaster-recovery snapshot, not a deployment bundle.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PARENT = PROJECT.parent
SOURCES = [
    (PROJECT, "rover_autonomy_ws", "rover_autonomy_ws"),
    (PARENT / "yolo_dataset", "references/unverified_original_yolo_dataset", "yolo_dataset"),
    (PARENT / "output/picar_validation", "references/picar_validation_history", "output/picar_validation"),
    (PARENT / "tmp/pdfs/build_picar_report.py", "references/build_picar_report.py", "tmp/pdfs/build_picar_report.py"),
    (PARENT / "picar 진행사항 정리.pdf", "references/picar_progress.pdf", "picar 진행사항 정리.pdf"),
    (PARENT / "ADR012-V5.1_PiCar-B_MarsRover_SmartCarKit_for_RPi-20260407.zip",
     "references/PiCar_B_MarsRover_vendor_20260407.zip",
     "ADR012-V5.1_PiCar-B_MarsRover_SmartCarKit_for_RPi-20260407.zip"),
]


def fail_walk(error):
    raise error


def files(source):
    if source.is_file():
        yield source, Path()
        return
    for folder, directories, names in os.walk(source, followlinks=False, onerror=fail_walk):
        if ".git" in directories:
            raise RuntimeError(f"Embedded Git metadata needs a separate archive: {folder}")
        for name in directories:
            path = Path(folder) / name
            if path.is_symlink():
                raise RuntimeError(f"Directory symlink requires an explicit archive: {path}")
        for name in sorted(names):
            path = Path(folder) / name
            if path.is_symlink():
                raise RuntimeError(f"File symlink requires an explicit archive: {path}")
            yield path, path.relative_to(source)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1048576), b""):
            value.update(block)
    return value.hexdigest()


def inventory():
    groups = []
    for source, target, restore in SOURCES:
        if not source.exists():
            raise FileNotFoundError(source)
        records = [(path, relative, path.stat().st_size) for path, relative in files(source)]
        groups.append({"source": str(source), "repository_path": target, "restore_path": restore,
                       "files": len(records), "bytes": sum(item[2] for item in records),
                       "largest": sorted([[str(item[1]), item[2]] for item in records],
                                         key=lambda item: item[1], reverse=True)[:3]})
    return groups


def prepare(destination):
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(PARENT):
        raise RuntimeError("Use a fresh backup directory outside the folder scheduled for deletion")
    groups = inventory()
    required = sum(group["bytes"] for group in groups)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free < required * 3 + 2 * 1024**3:
        raise RuntimeError("Need room for the backup, Git objects and independent restore verification")
    destination.mkdir()
    records = []
    directory_records = []
    secrets = []
    secret_patterns = (
        re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
        re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{50,}\b"),
        re.compile(rb"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----"),
    )
    for source, target, restore in SOURCES:
        if source.is_dir():
            for folder, _, _ in os.walk(source, followlinks=False, onerror=fail_walk):
                path = Path(folder)
                relative = path.relative_to(source)
                mapped = Path(target) / relative
                restored = Path(restore) / relative
                (destination / mapped).mkdir(parents=True, exist_ok=True)
                directory_records.append({"path": str(mapped).replace("\\", "/"),
                                          "restore_path": str(restored).replace("\\", "/"),
                                          "mtime_ns": path.stat().st_mtime_ns})
        for path, relative in files(source):
            mapped = Path(target) / relative if source.is_dir() else Path(target)
            restored = Path(restore) / relative if source.is_dir() else Path(restore)
            output = destination / mapped
            before = path.stat()
            if before.st_size >= 100 * 1048576:
                raise RuntimeError(f"GitHub single-file limit requires splitting: {mapped}")
            original = digest(path)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, output)
            if digest(output) != original or digest(path) != original:
                raise RuntimeError(f"Source changed or copy verification failed: {mapped}")
            if path.suffix.lower() in (".py", ".sh", ".ps1", ".json", ".yaml", ".yml", ".env", ".txt", ".log", ".md"):
                if before.st_size <= 8 * 1048576:
                    data = output.read_bytes()
                    if any(pattern.search(data) for pattern in secret_patterns):
                        secrets.append(str(mapped).replace("\\", "/"))
            records.append({"path": str(mapped).replace("\\", "/"),
                            "restore_path": str(restored).replace("\\", "/"),
                            "bytes": before.st_size, "sha256": original, "mtime_ns": before.st_mtime_ns})
            if len(records) % 1000 == 0:
                print(f"Copied and SHA-256 verified {len(records)} files", flush=True)
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(),
                "scope": "Complete local rover project plus explicit related references; no Pi-only originals",
                "pi_original_snapshot_included": False, "groups": groups, "files": records,
                "directories": directory_records,
                "total_files": len(records), "total_bytes": sum(item["bytes"] for item in records),
                "source_files_deleted": False}
    (destination / "BACKUP_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if secrets:
        (destination / "SECRET_REVIEW_REQUIRED.json").write_text(json.dumps(secrets, indent=2))
        raise RuntimeError("Potential credentials found; review file paths locally before any GitHub upload")
    (destination / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    print(json.dumps({"destination": str(destination), "files": manifest["total_files"],
                      "bytes": manifest["total_bytes"], "sha256_verified": True,
                      "secret_scan_hits": 0}, ensure_ascii=True, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.inspect:
        print(json.dumps(inventory(), ensure_ascii=True, indent=2))
    elif args.destination:
        prepare(args.destination)
    else:
        parser.error("--inspect or --destination is required")


if __name__ == "__main__":
    main()
