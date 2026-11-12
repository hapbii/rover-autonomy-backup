"""Optional training on an explicitly supplied dataset; never scans sibling folders."""

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/rover_autonomy"))
from rover_autonomy.vision.sign_classifier import LABELS, SignFeatures


def group_key(stem):
    parts = stem.split("_")
    if len(parts) < 2 or len(parts[1]) < 6:
        return stem
    stamp = parts[1]
    seconds = int(stamp[:2]) * 3600 + int(stamp[2:4]) * 60 + int(stamp[4:6])
    return f"{parts[0]}_{seconds // 10}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset", type=Path, required=True, help="Explicitly provided and verified YOLO dataset"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/new_sign_training")
    parser.add_argument("--epochs", type=int, default=220)
    args = parser.parse_args()
    rng = np.random.default_rng(5427)
    annotations = {}
    class_groups = defaultdict(set)
    for path in sorted(args.dataset.glob("*.txt")):
        if path.name == "classes.txt":
            continue
        rows = [
            list(map(float, row.split()))
            for row in path.read_text(encoding="utf-8").splitlines()
            if row.strip()
        ]
        annotations[path.stem] = rows
        for row in rows:
            class_groups[int(row[0])].add(group_key(path.stem))
    validation_groups = set()
    for label, groups in sorted(class_groups.items()):
        values = sorted(groups)
        rng.shuffle(values)
        if len(values) < 2:
            raise ValueError(f"Class {label} has fewer than two capture groups")
        validation_groups.update(values[: max(1, round(len(values) * 0.22))])
    # Groups containing multiple labels are never split between train and validation.
    validation_files = [name for name in annotations if group_key(name) in validation_groups]
    train_files = [name for name in annotations if name not in validation_files]
    features = SignFeatures()
    datasets = {"train": ([], []), "validation": ([], [])}
    begin = time.perf_counter()
    for number, (stem, rows) in enumerate(annotations.items()):
        image = cv2.imdecode(np.fromfile(args.dataset / f"{stem}.jpg", dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Unreadable image {stem}")
        height, width = image.shape[:2]
        split = "validation" if stem in validation_files else "train"
        x_values, y_values = datasets[split]
        boxes = []
        for raw in rows:
            label = int(raw[0])
            cx, cy, bw, bh = raw[1:]
            x1, y1 = max(0, int((cx - bw / 2) * width)), max(0, int((cy - bh / 2) * height))
            x2, y2 = min(width, int((cx + bw / 2) * width)), min(height, int((cy + bh / 2) * height))
            boxes.append((x1, y1, x2, y2))
            crop = image[y1:y2, x1:x2]
            if not crop.size:
                raise ValueError(f"Empty labeled crop {stem}")
            x_values.append(features.compute(crop))
            y_values.append(label)
            if split == "train":
                flipped = cv2.flip(crop, 1)
                flipped_label = 3 if label == 2 else 2 if label == 3 else label
                x_values.append(features.compute(flipped))
                y_values.append(flipped_label)
                for factor in (0.75, 1.2):
                    changed = np.clip(crop.astype(np.float32) * factor, 0, 255).astype(np.uint8)
                    x_values.append(features.compute(changed))
                    y_values.append(label)
        # Background crops never intersect any annotated sign. They remain in the same split.
        negatives = 0
        for _ in range(30):
            size = int(rng.integers(35, min(height, width) // 2))
            x, y = int(rng.integers(0, width - size)), int(rng.integers(0, height - size))
            if any(x < bx2 and x + size > bx1 and y < by2 and y + size > by1 for bx1, by1, bx2, by2 in boxes):
                continue
            x_values.append(features.compute(image[y : y + size, x : x + size]))
            y_values.append(4)
            negatives += 1
            if negatives == 3:
                break
        if number % 150 == 0:
            print(f"features {number}/{len(annotations)}", flush=True)
    x_train = np.asarray(datasets["train"][0], np.float32)
    y_train = np.asarray(datasets["train"][1], np.int32)
    x_val = np.asarray(datasets["validation"][0], np.float32)
    y_val = np.asarray(datasets["validation"][1], np.int32)
    if set(y_train) != set(range(5)) or set(y_val) != set(range(5)):
        raise ValueError("Both splits must contain every class")
    mean = x_train.mean(axis=0)
    scale = np.maximum(x_train.std(axis=0), 0.035)
    x_train = (x_train - mean) / scale
    x_val = (x_val - mean) / scale
    weights = np.zeros((x_train.shape[1], 5), np.float32)
    bias = np.zeros(5, np.float32)
    mw, vw = np.zeros_like(weights), np.zeros_like(weights)
    mb, vb = np.zeros_like(bias), np.zeros_like(bias)
    class_weights = len(y_train) / (5 * np.bincount(y_train, minlength=5))
    best = None
    best_loss = float("inf")
    stale = 0
    step = 0
    for epoch in range(args.epochs):
        indices = rng.permutation(len(y_train))
        for start in range(0, len(indices), 128):
            batch = indices[start : start + 128]
            x, y = x_train[batch], y_train[batch]
            logits = x @ weights + bias
            probabilities = np.exp(np.clip(logits - logits.max(axis=1, keepdims=True), -80, 0))
            probabilities /= probabilities.sum(axis=1, keepdims=True)
            probabilities[np.arange(len(y)), y] -= 1
            probabilities *= class_weights[y, None] / len(y)
            grad_w = x.T @ probabilities + 0.001 * weights
            grad_b = probabilities.sum(axis=0)
            step += 1
            mw = 0.9 * mw + 0.1 * grad_w
            vw = 0.999 * vw + 0.001 * grad_w * grad_w
            mb = 0.9 * mb + 0.1 * grad_b
            vb = 0.999 * vb + 0.001 * grad_b * grad_b
            weights -= 0.008 * (mw / (1 - 0.9**step)) / (np.sqrt(vw / (1 - 0.999**step)) + 1e-8)
            bias -= 0.008 * (mb / (1 - 0.9**step)) / (np.sqrt(vb / (1 - 0.999**step)) + 1e-8)
        logits = x_val @ weights + bias
        probs = np.exp(np.clip(logits - logits.max(axis=1, keepdims=True), -80, 0))
        probs /= probs.sum(axis=1, keepdims=True)
        loss = float(-np.log(np.maximum(probs[np.arange(len(y_val)), y_val], 1e-8)).mean())
        if loss < best_loss - 1e-4:
            best_loss = loss
            best = (weights.copy(), bias.copy(), epoch)
            stale = 0
        else:
            stale += 1
        if stale >= 25:
            break
    weights, bias, epoch = best
    labels = (x_val @ weights + bias).argmax(axis=1)
    confusion = np.zeros((5, 5), int)
    for truth, pred in zip(y_val, labels, strict=True):
        confusion[truth, pred] += 1
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "sign_classifier.npz", weights=weights, bias=bias, mean=mean, scale=scale)
    report = {
        "labels": LABELS,
        "split": "Whole 10-second capture groups; split before crop augmentation",
        "train_files": train_files,
        "validation_files": validation_files,
        "train_groups": sorted({group_key(name) for name in train_files}),
        "validation_groups": sorted(validation_groups),
        "train_samples": dict(Counter(map(int, y_train))),
        "validation_samples": dict(Counter(map(int, y_val))),
        "validation_crop_accuracy": float((labels == y_val).mean()),
        "confusion": confusion.tolist(),
        "best_epoch": epoch,
        "elapsed_seconds": time.perf_counter() - begin,
        "limitations": "Small same-room dataset; grouped validation is not a new-room road test. Evaluate full-frame proposals separately.",
    }
    (out / "sign_training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in report.items() if not k.endswith("files") and not k.endswith("groups")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
