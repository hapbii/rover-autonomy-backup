"""Install a verified Arduino CLI into this workspace, never into system folders."""

import hashlib
import io
import json
import os
import subprocess
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "rover-autonomy-local-build"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def arduino_environment():
    env = os.environ.copy()
    env["ARDUINO_DIRECTORIES_DATA"] = str(ROOT / "tools/arduino-data")
    env["ARDUINO_DIRECTORIES_DOWNLOADS"] = str(ROOT / "tools/cache")
    env["ARDUINO_DIRECTORIES_USER"] = str(ROOT / "tools/arduino-user")
    env["ARDUINO_UPDATER_ENABLE_NOTIFICATION"] = "false"
    return env


def main():
    if os.name != "nt":
        raise SystemExit("Local bootstrap is for Windows; on Pi use an installed arduino-cli")
    tools = ROOT / "tools"
    tools.mkdir(exist_ok=True)
    binary = tools / "arduino-cli.exe"
    if not binary.exists():
        release = json.loads(
            download("https://api.github.com/repos/arduino/arduino-cli/releases/tags/v1.6.0")
        )
        asset = next(item for item in release["assets"] if item["name"].endswith("Windows_64bit.zip"))
        checks = next(item for item in release["assets"] if "checksums" in item["name"])
        data = download(asset["browser_download_url"])
        sums = download(checks["browser_download_url"]).decode()
        expected = next(
            row.split()[0] for row in sums.splitlines() if row.split()[-1].lstrip("*") == asset["name"]
        )
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Arduino CLI checksum mismatch")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            member = next(name for name in archive.namelist() if name.endswith("arduino-cli.exe"))
            binary.write_bytes(archive.read(member))
    env = arduino_environment()
    subprocess.run([str(binary), "core", "update-index"], env=env, check=True)
    subprocess.run([str(binary), "core", "install", "arduino:avr@1.8.8"], env=env, check=True)
    print("Arduino compiler ready; no board upload was performed.")


if __name__ == "__main__":
    main()
