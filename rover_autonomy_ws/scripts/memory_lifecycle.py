"""Repeat real model/decoder startup and shutdown, without opening physical devices.

Uses a generated local video, the public palm model/reference, and an in-memory
serial transport. ROS DDS and libcamera require a separate Raspberry Pi soak.
"""

import argparse
import gc
import json
import sys
import tempfile
import time
import tracemalloc
from contextlib import ExitStack, closing
from pathlib import Path

import cv2
import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/rover_autonomy"))
from memory_soak import BoundedWire
from rover_autonomy.hardware.camera import OpenCVCamera
from rover_autonomy.hardware.protocol import SerialLink
from rover_autonomy.vision.hands import PalmDetector
from rover_autonomy.vision.pipeline import PerceptionPipeline

from rover_autonomy.config import HardwareConfig


def snapshot(process):
    gc.collect()
    return {
        "rss": process.memory_info().rss,
        "traced": tracemalloc.get_traced_memory()[0],
        "handles": process.num_handles() if hasattr(process, "num_handles") else process.num_fds(),
        "threads": process.num_threads(),
        "objects": len(gc.get_objects()),
    }


def write_video(path, reference):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 12, (320, 240))
    try:
        if not writer.isOpened():
            raise RuntimeError("Lifecycle input video could not be created")
        frame = cv2.resize(reference, (320, 240))
        for _ in range(3):
            writer.write(frame)
    finally:
        writer.release()


def one_cycle(video, config):
    with ExitStack() as resources:
        pipeline = resources.enter_context(
            closing(
                PerceptionPipeline(
                    palm=PalmDetector(
                        ROOT / "src/rover_autonomy/models/palm_detection_mediapipe_2023feb.onnx"
                    )
                )
            )
        )
        camera = resources.enter_context(closing(OpenCVCamera(str(video), 320, 240, 12)))
        wire = BoundedWire()
        link = resources.enter_context(closing(SerialLink("virtual only", config, 0, wire)))
        link.set_arm(False)
        link.tick(2.1)
        link.tick(2.2)
        link.tick(2.3)
        if link.state != "configured":
            raise AssertionError("In-memory lifecycle handshake failed")
        frame = camera.read()
        observed = pipeline.process(frame, 1, 2.3, hand_enabled=True)
        if observed.hand is None:
            raise AssertionError("Lifecycle palm inference did not detect the reference")
        forwards = pipeline.palm.inference_count
    if camera.capture is not None or pipeline.palm is not None or link.transport is not None:
        raise AssertionError("A closed owner retained a resource")
    if not wire.closed:
        raise AssertionError("Serial transport was not closed")
    return forwards


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=400)
    parser.add_argument("--warmup", type=int, default=200)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/memory_lifecycle_report.json")
    args = parser.parse_args()
    if args.cycles < 20 or args.warmup < 5:
        parser.error("cycles >= 20 and warmup >= 5 are required")
    cv2.setNumThreads(1)
    reference = cv2.imdecode(np.fromfile(ROOT / "tests/assets/palm_reference.png", np.uint8), 1)
    if reference is None:
        raise ValueError("Public palm reference image missing")
    config = HardwareConfig(
        enabled=True, calibrated=True, wheel_radius_m=0.03, track_width_m=0.2, encoder_ticks_per_rev=960
    )
    process = psutil.Process()
    forwards = 0
    samples = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="rover_lifecycle_") as directory:
        video = Path(directory) / "reference.mp4"
        write_video(video, reference)
        with closing(OpenCVCamera(str(video), 320, 240, 12)) as camera:
            decoder_backend = camera.capture.getBackendName()
            decoder_threads = int(camera.capture.get(cv2.CAP_PROP_N_THREADS))
        tracemalloc.start()
        try:
            for _ in range(args.warmup):
                forwards += one_cycle(video, config)
            before = tracemalloc.take_snapshot()
            baseline = snapshot(process)
            for cycle in range(1, args.cycles + 1):
                forwards += one_cycle(video, config)
                if cycle % 10 == 0 or cycle == args.cycles:
                    samples.append({"cycles": cycle, **snapshot(process)})
                if cycle % 50 == 0:
                    print(f"lifecycle {cycle}/{args.cycles}", flush=True)
            final = snapshot(process)
            after = tracemalloc.take_snapshot()
            growth = {key: final[key] - baseline[key] for key in baseline}
            passed = (
                growth["traced"] < 2 * 1048576
                and growth["rss"] < 24 * 1048576
                and growth["handles"] <= 2
                and growth["threads"] <= 1
            )
            result = {
                "warmup_cycles": args.warmup,
                "measured_cycles": args.cycles,
                "real_palm_inferences": forwards,
                "decoder_backend": decoder_backend,
                "decoder_threads": decoder_threads,
                "elapsed_seconds": time.perf_counter() - started,
                "baseline": baseline,
                "final": final,
                "growth": growth,
                "samples": samples,
                "python_top_growth": [
                    {"location": str(item.traceback), "bytes": item.size_diff, "count": item.count_diff}
                    for item in after.compare_to(before, "lineno")[:8]
                ],
                "thresholds": {
                    "retained_python_bytes": 2 * 1048576,
                    "rss_growth_bytes": 24 * 1048576,
                    "handle_growth": 2,
                    "thread_growth": 1,
                },
                "scope": "Actual repeated ONNX and local MP4 decoder lifecycle; virtual serial. No physical camera, USB serial, ROS DDS or Pi libcamera.",
                "passed": passed,
            }
        finally:
            tracemalloc.stop()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {key: result[key] for key in ("measured_cycles", "real_palm_inferences", "growth", "passed")},
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
