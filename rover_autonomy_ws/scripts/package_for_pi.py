"""Build an additive SSH transfer bundle, excluding caches and unverified experiments."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = []
    for folder in ("src", "firmware", "scripts", "tests", "docs"):
        base = ROOT / folder
        if base.exists():
            paths += [
                path
                for path in base.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
                and not any(part.endswith(".egg-info") for part in path.parts)
            ]
    for pattern in ("*.md", "*.sh", "requirements*.txt", "pyproject.toml", "LICENSE"):
        paths += list(ROOT.glob(pattern))
    for relative in (
        "artifacts/demo/report.json",
        "artifacts/memory_report.json",
        "artifacts/memory_lifecycle_report.json",
        "artifacts/sign_synthetic_report.json",
        "artifacts/environment_report.json",
        "artifacts/test_report.xml",
        "artifacts/firmware/build_report.txt",
        "artifacts/pin_migration_20261113/test_report.xml",
        "artifacts/uart_deployment/backup.json",
        "artifacts/uart_deployment/pwm_zero_watchdog.json",
        "artifacts/uart_deployment/ros_simulation.json",
        "artifacts/uart_deployment/ros_image.json",
        "artifacts/uart_deployment/camera_python.json",
        "artifacts/uart_deployment/camera_ros.json",
        "artifacts/uart_deployment/camera_native.json",
        "artifacts/uart_deployment/environment.json",
        "artifacts/uart_deployment/pi_test_report.xml",
    ):
        path = ROOT / relative
        if path.is_file():
            paths.append(path)
    # Never ship stale RA1/EM2 binaries from earlier builds with the new sensor wiring.
    paths += list((ROOT / "artifacts/firmware").glob("rover_sensors.ino*.hex"))
    for pattern in ("*.json", "*.xml"):
        paths += list((ROOT / "artifacts/pi_deployment").glob(pattern))
    unique = sorted(set(paths))
    for path in unique:
        relative = path.relative_to(ROOT)
        if "experiments" in relative.parts or path.suffix == ".npz":
            raise ValueError("Unverified experimental training data must not enter deployment")
    manifest = {
        str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in unique
    }
    destination = ROOT / "artifacts/rover_autonomy_pi_bundle.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in unique:
            relative = path.relative_to(ROOT)
            archive.write(path, str(Path("rover_autonomy_ws") / relative))
        archive.writestr("rover_autonomy_ws/TRANSFER_MANIFEST.json", json.dumps(manifest, indent=2))
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert not any(
            "experiments/" in name or "yolo_dataset/" in name or name.endswith(".npz")
            for name in archive.namelist()
        )
    report = {
        "file": destination.name,
        "bytes": destination.stat().st_size,
        "files": len(unique),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "uploaded": False,
        "excludes": [".venv", "tools", "experiments", "unverified source photos/models", "demo MP4s"],
    }
    (destination.parent / "bundle_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
