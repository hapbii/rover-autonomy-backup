"""Mixed vision/control/serial stress test; reports retained Python and native RSS.

Warm-up includes both image sizes and real palm inference before the baseline.
The simulated serial wire is bounded too, so the test itself does not invent a leak.
"""

import argparse
import gc
import json
import sys
import time
import tracemalloc
from collections import deque
from contextlib import ExitStack
from pathlib import Path

import cv2
import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/rover_autonomy"))
from rover_autonomy.control.supervisor import Supervisor
from rover_autonomy.hardware.protocol import READY, SerialLink
from rover_autonomy.simulation import World
from rover_autonomy.transport import decode_vision, encode_vision
from rover_autonomy.types import Mode, Range
from rover_autonomy.vision.hands import PalmDetector
from rover_autonomy.vision.pipeline import PerceptionPipeline

from rover_autonomy.config import HardwareConfig


class BoundedWire:
    def __init__(self):
        self.incoming = bytearray()
        self.sequence = 0
        self.recent = deque(maxlen=4)
        self.closed = False
        self.armed = False

    def write(self, data):
        text = data.decode().strip()
        self.recent.append(text)
        reply = ""
        if text == "HELLO":
            reply = READY + "\n"
        elif text.startswith("CFG "):
            reply = "RA1 CONFIGURED\n"
        elif text == "ARM":
            self.armed = True
            reply = "RA1 ARMED\n"
        elif text == "STOP":
            self.armed = False
            reply = "RA1 STOPPED\n"
        reply += f"T {self.sequence} 0 0 0 0 0 0 0 0 2000 {5 if self.armed else 4}\n"
        self.sequence += 1
        self.incoming.extend(reply.encode())
        if len(self.incoming) > 4096:
            raise AssertionError("Test wire queue unexpectedly grew")
        return len(data)

    def read(self, size):
        data = bytes(self.incoming[:size])
        del self.incoming[:size]
        return data

    def close(self):
        self.closed = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=12000)
    parser.add_argument("--warmup", type=int, default=1200)
    parser.add_argument("--hand-stride", type=int, default=8)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/memory_report.json")
    args = parser.parse_args()
    if args.frames < 1000 or args.warmup < 128 or args.hand_stride < 1:
        parser.error("frames >= 1000, warmup >= 128, hand-stride >= 1 are required")
    with ExitStack() as resources:
        return run(args, resources)


def run(args, resources):
    cv2.setNumThreads(1)
    reference = cv2.imdecode(np.fromfile(ROOT / "tests/assets/palm_reference.png", np.uint8), 1)
    near_reference = cv2.resize(reference[150:450, 250:550], (320, 240))
    palm = PalmDetector(ROOT / "src/rover_autonomy/models/palm_detection_mediapipe_2023feb.onnx")
    pipeline = PerceptionPipeline(palm=palm)
    resources.callback(pipeline.close)
    world = World()
    controller = Supervisor()
    controller.set_mode(Mode.LINE)
    controller.set_armed(True)
    config = HardwareConfig(
        enabled=True, calibrated=True, wheel_radius_m=0.03, track_width_m=0.2, encoder_ticks_per_rev=960
    )
    wire = BoundedWire()
    link = SerialLink("virtual only", config, 0, wire)
    resources.callback(link.close)
    link.set_arm(False)
    process = psutil.Process()
    samples = deque(maxlen=256)
    durations = deque(maxlen=1024)
    baseline = None
    # Trace through warm-up too: otherwise replacement of pre-trace arrays looks
    # like retained growth even when the same single frame is merely replaced.
    tracemalloc.start()
    resources.callback(tracemalloc.stop)
    start_time = time.perf_counter()
    try:
        for index in range(args.frames + args.warmup):
            begin = time.perf_counter()
            now = 2.1 + index * 0.05
            use_hand = index % args.hand_stride == 0
            frame = (
                (near_reference if (index // args.hand_stride) % 2 == 0 else reference)
                if use_hand
                else world.frame()
            )
            observation = pipeline.process(frame, index + 1, now, use_hand)
            observation = decode_vision(encode_vision(observation, now), now)
            controller.set_mode(Mode.HAND if use_hand else Mode.LINE)
            controller.update_vision(observation)
            controller.update_range(Range(2.0, now))
            controller.update_odometry(world.odometry(now))
            command = controller.tick(now)
            world.advance(command, 0.01)
            link.tick(now)
            if link.state == "configured":
                link.set_arm(True)
            if link.state == "fault":
                raise AssertionError(link.fault)
            durations.append((time.perf_counter() - begin) * 1000)
            if index == args.warmup - 1:
                gc.collect()
                before = tracemalloc.take_snapshot()
                baseline = {
                    "rss": process.memory_info().rss,
                    "traced": tracemalloc.get_traced_memory()[0],
                    "objects": len(gc.get_objects()),
                    "threads": process.num_threads(),
                    "handles": process.num_handles()
                    if hasattr(process, "num_handles")
                    else process.num_fds(),
                }
            elif index >= args.warmup and (index - args.warmup + 1) % 500 == 0:
                gc.collect()
                sample = {
                    "frames": index - args.warmup + 1,
                    "rss": process.memory_info().rss,
                    "traced": tracemalloc.get_traced_memory()[0],
                }
                samples.append(sample)
                if (index - args.warmup + 1) % 3000 == 0:
                    print(
                        f"soak {index - args.warmup + 1}/{args.frames}, rss={sample['rss'] / 1048576:.1f} MiB",
                        flush=True,
                    )
        gc.collect()
        final = {
            "rss": process.memory_info().rss,
            "traced": tracemalloc.get_traced_memory()[0],
            "objects": len(gc.get_objects()),
            "threads": process.num_threads(),
            "handles": process.num_handles() if hasattr(process, "num_handles") else process.num_fds(),
        }
        after = tracemalloc.take_snapshot()
        growth = {key: final[key] - baseline[key] for key in baseline}
        result = {
            "frames_after_warmup": args.frames,
            "warmup_frames": args.warmup,
            "hand_stride": args.hand_stride,
            "real_palm_inferences": palm.inference_count,
            "elapsed_seconds": time.perf_counter() - start_time,
            "baseline": baseline,
            "final": final,
            "growth": growth,
            "samples": list(samples),
            "tail_traced_growth": int(
                np.median([sample["traced"] for sample in list(samples)[-max(1, len(samples) // 4) :]])
                - np.median([sample["traced"] for sample in list(samples)[: max(1, len(samples) // 4)]])
            ),
            "processing_ms_recent_median": float(np.median(durations)),
            "processing_ms_recent_p95": float(np.percentile(durations, 95)),
            "bounded_state": {
                "camera_observations": 1,
                "sign_history": len(controller.signs.history),
                "serial_rx_buffer": len(link.buffer),
                "test_wire_queue": len(wire.incoming),
                "test_wire_history": len(wire.recent),
            },
            "python_top_growth": [
                {"location": str(item.traceback), "bytes": item.size_diff, "count": item.count_diff}
                for item in after.compare_to(before, "lineno")[:8]
            ],
            "thresholds": {
                "retained_python_bytes": 2 * 1048576,
                "rss_growth_bytes": 24 * 1048576,
                "handle_growth": 2,
                "tail_retained_python_bytes": 256 * 1024,
            },
            "scope": "Windows local process; real OpenCV models and core logic, virtual serial, no ROS middleware/Pi camera/native Pi driver soak.",
        }
        result["passed"] = (
            growth["traced"] < 2 * 1048576
            and growth["rss"] < 24 * 1048576
            and growth["handles"] <= 2
            and result["tail_traced_growth"] < 256 * 1024
        )
    finally:
        # ExitStack runs every cleanup even if one resource's close raises.
        resources.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "frames_after_warmup",
                    "real_palm_inferences",
                    "elapsed_seconds",
                    "growth",
                    "bounded_state",
                    "passed",
                )
            },
            indent=2,
        )
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
