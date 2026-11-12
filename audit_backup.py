"""Check the snapshot against both its manifest and original local files."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1048576), b""):
            value.update(block)
    return value.hexdigest()


def main():
    manifest_path = ROOT / "BACKUP_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {item["path"]: item for item in manifest["files"]}
    found = set()
    for group in manifest["groups"]:
        source = Path(group["source"])
        if source.is_file():
            paths = [(source, Path())]
        else:
            paths = []
            errors = []
            for folder, _, names in os.walk(source, followlinks=False, onerror=errors.append):
                paths += [(Path(folder) / name, (Path(folder) / name).relative_to(source)) for name in names]
            if errors:
                raise RuntimeError("Original file inventory failed")
        for path, relative in paths:
            mapped = (Path(group["repository_path"]) / relative).as_posix()
            record = expected.get(mapped)
            if record is None or digest(path) != record["sha256"] or digest(ROOT / mapped) != record["sha256"]:
                raise RuntimeError(f"Missing, changed or mismatched source: {mapped}")
            found.add(mapped)
    if found != set(expected):
        raise RuntimeError("The manifest and original file lists differ")
    result = {"at": datetime.now(timezone.utc).isoformat(), "original_files_verified": len(found),
              "verified_bytes": manifest["total_bytes"], "source_to_copy_sha256_passed": True,
              "manifest_sha256": digest(manifest_path), "pi_original_snapshot_included": False,
              "source_files_deleted": False}
    (ROOT / "BACKUP_AUDIT.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
