"""Optional real-image evaluation; requires an explicitly provided labeled dataset."""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/rover_autonomy"))
from rover_autonomy.types import Sign
from rover_autonomy.vision.signs import SignDetector

NAMES = [Sign.GREEN, Sign.RED, Sign.LEFT, Sign.RIGHT]


def read_image(path):
    # cv2.imread on Windows does not reliably support Unicode paths.
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)


def overlap(a, b):
    x = max(a[0], b[0])
    y = max(a[1], b[1])
    right = min(a[0] + a[2], b[0] + b[2])
    bottom = min(a[1] + a[3], b[1] + b[3])
    intersection = max(0, right - x) * max(0, bottom - y)
    return intersection / max(1, a[2] * a[3] + b[2] * b[3] - intersection)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/sign_evaluation")
    parser.add_argument("--backend", choices=("geometry", "experimental_hog"), default="geometry")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--all-images", action="store_true")
    parser.add_argument("--iou", type=float, default=0.5)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.backend == "experimental_hog" and args.model is None:
        parser.error("--backend experimental_hog requires an explicit --model")
    detector = SignDetector(use_classifier=args.backend == "experimental_hog", model_path=args.model)
    split_path = args.split_manifest
    validation_files = None
    if split_path is not None and split_path.exists() and not args.all_images:
        validation_files = set(json.loads(split_path.read_text(encoding="utf-8"))["validation_files"])
    totals = Counter()
    correct = Counter()
    missing = []
    wrong = []
    latency = []
    strict_tp = 0
    predictions = 0
    truth_count = 0
    examples = set()
    example_count = 0
    for text in sorted(args.dataset.glob("*.txt")):
        if text.name == "classes.txt":
            continue
        if validation_files is not None and text.stem not in validation_files:
            continue
        image = read_image(text.with_suffix(".jpg"))
        if image is None:
            missing.append(text.stem)
            continue
        h, w = image.shape[:2]
        truth = []
        for line in text.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            label = NAMES[int(fields[0])]
            cx, cy, bw, bh = map(float, fields[1:])
            truth.append((label, ((cx - bw / 2) * w, (cy - bh / 2) * h, bw * w, bh * h)))
            totals[label.value] += 1
        begin = time.perf_counter()
        found = detector.detect(image)
        latency.append((time.perf_counter() - begin) * 1000)
        predictions += len(found)
        truth_count += len(truth)
        used = set()
        for label, box in truth:
            matches = [
                (index, item)
                for index, item in enumerate(found)
                if item.label == label and index not in used and overlap(item.box, box) >= args.iou
            ]
            if matches:
                index, item = max(matches, key=lambda pair: overlap(pair[1].box, box))
                strict_tp += 1
                used.add(index)
                correct[label.value] += 1
            else:
                wrong.append(
                    {
                        "file": text.stem,
                        "truth": label.value,
                        "predicted": [item.label.value for item in found],
                    }
                )
            if example_count < 8 and (label not in examples or not matches):
                annotated = image.copy()
                for item in found:
                    x, y, bw, bh = item.box
                    cv2.rectangle(annotated, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
                    cv2.putText(
                        annotated,
                        f"{item.label}:{item.confidence:.2f}",
                        (x, max(15, y)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        1,
                    )
                ok, data = cv2.imencode(".jpg", annotated)
                if ok:
                    (args.output / f"example_{label.value}_{text.stem}.jpg").write_bytes(data.tobytes())
                examples.add(label)
                example_count += 1
    result = {
        "dataset": str(args.dataset),
        "method": "HSV proposals + experimental HOG/color softmax"
        if args.backend == "experimental_hog"
        else "HSV + geometry (no training)",
        "evaluation": f"Training-separated development validation; 10-second groups; IoU >= {args.iou}, class matched, one-to-one"
        if validation_files is not None
        else f"All images (may include training); IoU >= {args.iou}, class matched, one-to-one",
        "ground_truth": truth_count,
        "predictions": predictions,
        "true_positives": strict_tp,
        "precision": strict_tp / max(1, predictions),
        "recall": strict_tp / max(1, truth_count),
        "per_class": {
            name: {
                "total": totals[name],
                "correct": correct[name],
                "recall": correct[name] / max(1, totals[name]),
            }
            for name in totals
        },
        "latency_ms_median": float(np.median(latency)),
        "latency_ms_p95": float(np.percentile(latency, 95)),
        "missing_images": missing,
        "missed_detections": wrong,
        "limitations": "Controlled dataset scenes are not proof of generalization to a different room, lighting or sign design.",
    }
    (args.output / "report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in ("dataset", "missed_detections")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
