"""Run the real perception/controller locally with a simulated chassis and sonar.

No ROS, serial device or physical camera is opened. Each scenario writes an MP4,
four inspection stills and a compact result report.
"""

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from contextlib import ExitStack
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/rover_autonomy"))
from rover_autonomy.control.supervisor import Supervisor
from rover_autonomy.simulation import World
from rover_autonomy.types import Mode, Range
from rover_autonomy.vision.hands import PalmDetector
from rover_autonomy.vision.pipeline import PerceptionPipeline


def read_image(path):
    result = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if result is None:
        raise ValueError(f"Cannot read {path}")
    return result


def overlay_sign(frame, name):
    crop = read_image(ROOT / f"tests/assets/sign_{name}.png")
    height = 105
    width = round(crop.shape[1] * height / crop.shape[0])
    resized = cv2.resize(crop, (width, height))
    x = 210 if width < 100 else 160
    frame[12 : 12 + height, x : x + width] = resized


def run_case(name, destination):
    with ExitStack() as resources:
        return _run_case(name, destination, resources)


def _run_case(name, destination, resources):
    world = World(y=-0.10 if name == "line_follow" else 0, obstacle_enabled=name == "obstacle")
    controller = Supervisor()
    controller.set_mode(Mode.HAND if name == "hand_follow" else Mode.AUTONOMOUS)
    controller.set_armed(True)
    palm = (
        PalmDetector(ROOT / "src/rover_autonomy/models/palm_detection_mediapipe_2023feb.onnx")
        if name == "hand_follow"
        else None
    )
    pipeline = PerceptionPipeline(palm=palm)
    resources.callback(pipeline.close)
    reference = read_image(ROOT / "tests/assets/palm_reference.png") if palm else None
    reasons = Counter()
    seen_signs = Counter()
    snapshots = []
    turns = []
    avoidance_phases = set()
    minimum_range = 4.0
    maximum_forward = 0.0
    frames = 650 if name == "obstacle" else 180
    handle, temp_name = tempfile.mkstemp(prefix="rover_demo_", suffix=".mp4")
    os.close(handle)
    resources.callback(Path(temp_name).unlink, missing_ok=True)
    writer_cleanup = resources.enter_context(ExitStack())
    writer = cv2.VideoWriter(temp_name, cv2.VideoWriter_fourcc(*"mp4v"), 20, (320, 240))
    writer_cleanup.callback(writer.release)
    if not writer.isOpened():
        raise RuntimeError("MP4 writer could not be opened")
    try:
        for step in range(frames):
            now = 1 + step * 0.05
            frame = world.frame()
            if name == "red_green":
                if 20 <= step < 70:
                    overlay_sign(frame, "red_light")
                elif 80 <= step < 130:
                    overlay_sign(frame, "green_light")
            elif name in ("left_turn", "right_turn") and step >= 10:
                overlay_sign(frame, "left" if name == "left_turn" else "right")
            elif name == "hand_follow":
                if step < 50:
                    frame = cv2.flip(reference, 1)
                elif step < 100:
                    frame = reference.copy()
                elif step < 145:
                    frame = cv2.resize(reference[150:450, 250:550], (320, 240))
            if name != "sensor_loss" or step < 30:
                observation = pipeline.process(frame, step + 1, now, palm is not None)
                controller.update_vision(observation)
                controller.update_range(Range(world.distance(), now))
                for detected in observation.signs:
                    seen_signs[detected.label.value] += 1
            controller.update_odometry(world.odometry(now))
            if name == "emergency" and step >= 30:
                controller.emergency = True
            command = controller.tick(now)
            reasons[command.reason] += 1
            avoidance_phases.add(controller.avoidance.state)
            minimum_range = min(minimum_range, world.distance())
            maximum_forward = max(maximum_forward, command.linear)
            world.advance(command, 0.05)
            rendered = cv2.resize(frame, (320, 240))
            cv2.rectangle(rendered, (0, 0), (320, 36), (40, 40, 40), -1)
            cv2.putText(rendered, name, (5, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            cv2.putText(rendered, command.reason, (5, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.34, (255, 255, 255), 1)
            cv2.putText(
                rendered,
                f"v={command.linear:.3f} w={command.angular:.3f} sonar={world.distance():.2f}m",
                (3, 232),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                (255, 20, 20),
                1,
            )
            writer.write(rendered)
            if step in (0, 35, 95, frames - 1) or command.reason == "sign_turn_complete":
                if len(snapshots) < 5:
                    snapshots.append(rendered.copy())
            if command.reason == "sign_turn_complete":
                turns.append(world.yaw)
                break
    finally:
        controller.set_armed(False)
        writer_cleanup.close()
    Path(temp_name).replace(destination / f"{name}.mp4")
    for index, image in enumerate(snapshots):
        ok, data = cv2.imencode(".png", image)
        if ok:
            (destination / f"{name}_{index}.png").write_bytes(data.tobytes())
    checks = {
        "line_follow": maximum_forward > 0 and abs(world.y) < 0.10,
        "red_green": reasons["red_light_stop"] > 0
        and seen_signs["green_light"] >= 3
        and reasons["camera_line_follow"] > 0,
        "left_turn": bool(turns) and turns[-1] > 1.3,
        "right_turn": bool(turns) and turns[-1] < -1.3,
        "obstacle": "advance" in avoidance_phases
        and "done" in avoidance_phases
        and "failed" not in avoidance_phases,
        "hand_follow": reasons["hand_follow_relative_palm_size"] > 0
        and reasons["hand_too_close"] > 0
        and reasons["hand_lost"] > 0,
        "sensor_loss": reasons["camera_stale"] > 0,
        "emergency": reasons["emergency_stop"] > 0,
    }
    return {
        "scenario": name,
        "passed": bool(checks[name]),
        "reasons": dict(reasons),
        "detected_signs": dict(seen_signs),
        "avoidance_states": sorted(avoidance_phases),
        "final_pose": [world.x, world.y, world.yaw],
        "minimum_sonar_m": minimum_range,
        "max_forward_m_s": maximum_forward,
        "simulation_only": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/demo")
    parser.add_argument("--scenario", default="all")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    names = (
        [
            "line_follow",
            "red_green",
            "left_turn",
            "right_turn",
            "obstacle",
            "hand_follow",
            "sensor_loss",
            "emergency",
        ]
        if args.scenario == "all"
        else [args.scenario]
    )
    results = []
    for name in names:
        result = run_case(name, args.output)
        results.append(result)
        print(f"{name}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)
    report = {
        "scope": "Real local perception/controller + simulated chassis/sonar. No ROS runtime or physical vehicle test.",
        "sign_inputs": "synthetic graphics generated by scripts/make_synthetic_assets.py; no project photographs",
        "hand_inputs": "Apache-2.0 OpenCV Zoo reference image and pretrained palm model",
        "real_sign_accuracy_measured": False,
        "results": results,
        "passed": all(item["passed"] for item in results),
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
