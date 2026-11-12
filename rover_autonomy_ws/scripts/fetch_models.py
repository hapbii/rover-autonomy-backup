"""Download the Apache-2.0 OpenCV Zoo palm model with Git-LFS SHA-256 verification."""

import hashlib
import json
import urllib.request
from pathlib import Path


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "rover-autonomy-local-build"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / "src/rover_autonomy/models"
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "palm_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        commit = manifest["commit"]
    else:
        commit = json.loads(fetch("https://api.github.com/repos/opencv/opencv_zoo/commits/main"))["sha"]
    model = "models/palm_detection_mediapipe/palm_detection_mediapipe_2023feb.onnx"
    pointer = fetch(f"https://raw.githubusercontent.com/opencv/opencv_zoo/{commit}/{model}").decode()
    expected = next(
        line.split("sha256:")[1] for line in pointer.splitlines() if line.startswith("oid sha256:")
    )
    path = destination / Path(model).name
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        data = fetch(f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{commit}/{model}")
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Palm model SHA-256 mismatch")
        path.write_bytes(data)
    license_url = f"https://raw.githubusercontent.com/opencv/opencv_zoo/{commit}/models/palm_detection_mediapipe/LICENSE"
    (destination / "PALM_LICENSE.txt").write_bytes(fetch(license_url))
    manifest = {
        "commit": commit,
        "file": path.name,
        "sha256": expected,
        "license": "Apache-2.0",
        "source": model,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
