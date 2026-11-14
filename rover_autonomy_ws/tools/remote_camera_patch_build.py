"""Isolated libcamera 0.2.0 build with upstream's embedded-buffer initialization fix."""
import json
import os
import subprocess
from pathlib import Path

support = Path.home() / "rover_support"
source = support / "libcamera-v0.2.0-fixed"
support.mkdir(exist_ok=True)


def run(args, **kwargs):
    print("RUN", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, **kwargs)


if not source.exists():
    run(["git", "clone", "--depth", "1", "--branch", "v0.2.0",
         "https://github.com/libcamera-org/libcamera.git", source])
file = source / "src/libcamera/pipeline/rpi/vc4/vc4.cpp"
text = file.read_text()
needle = "ipa::RPi::PrepareParams params;"
replacement = needle + "\n\tparams.buffers.embedded = 0; // upstream Jan 2024 initialization fix"
if replacement not in text:
    if text.count(needle) != 1:
        raise RuntimeError("Unexpected pipeline source")
    file.write_text(text.replace(needle, replacement))
if not (source / "build/build.ninja").exists():
    run(["meson", "setup", "build", "-Dpipelines=rpi/vc4", "-Dipas=rpi/vc4",
         "-Dcam=enabled", "-Dqcam=disabled", "-Dgstreamer=disabled", "-Dpycamera=enabled",
         "-Dtest=false", "-Ddocumentation=disabled", "-Dlc-compliance=disabled", "-Dtracing=disabled"], cwd=source)
run(["ninja", "-C", "build", "-j2"], cwd=source)
environment = os.environ.copy()
environment.pop("LD_LIBRARY_PATH", None)
environment.pop("LIBCAMERA_IPA_MODULE_PATH", None)
run([source / "build/src/apps/cam/cam", "-l"], env=environment)
run([source / "build/src/apps/cam/cam", "-c", "1", "--capture=3",
     "--file=" + str(support / "patched_camera_frame-#.raw")], env=environment, timeout=25)
(support / "camera_patch_build.json").write_text(json.dumps({
    "source": str(source), "version": "0.2.0", "capture_frames": 3,
    "fix": "Initialize params.buffers.embedded before conditional assignment",
    "upstream": "https://lists.libcamera.org/pipermail/libcamera-devel/2024-January/040367.html",
    "system_libraries_replaced": False,
}, indent=2))
print("CAMERA_PATCH_CAPTURE_OK", flush=True)
