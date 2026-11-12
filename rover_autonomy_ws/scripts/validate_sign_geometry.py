"""Synthetic geometry regression report. This does not measure camera/photo accuracy."""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from make_synthetic_assets import sign_image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/rover_autonomy"))
from rover_autonomy.vision.signs import SignDetector


def main():
    detector = SignDetector()
    cases = 0
    failures = []
    for label in ("green_light", "red_light", "left", "right"):
        for white in (False, True) if label in ("left", "right") else (False,):
            crop = sign_image(label, white_arrow=white)
            for height in (80, 110, 140):
                for angle in (-8, 0, 8):
                    for brightness in (0.75, 1.0, 1.15):
                        width = round(crop.shape[1] * height / crop.shape[0])
                        resized = cv2.resize(crop, (width, height))
                        rotated = cv2.warpAffine(
                            resized,
                            cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1),
                            (width, height),
                            borderValue=(230, 230, 230),
                        )
                        canvas = np.full((240, 320, 3), 230, np.uint8)
                        x = (320 - width) // 2
                        canvas[15 : 15 + height, x : x + width] = rotated
                        canvas = np.clip(canvas.astype(np.float32) * brightness, 0, 255).astype(np.uint8)
                        found = detector.detect(canvas)
                        cases += 1
                        if not any(item.label.value == label for item in found):
                            failures.append(
                                {
                                    "label": label,
                                    "white_arrow": white,
                                    "height": height,
                                    "rotation": angle,
                                    "brightness": brightness,
                                }
                            )
    report = {
        "kind": "synthetic geometry regression only",
        "training_used": False,
        "real_photographs": 0,
        "cases": cases,
        "passed_cases": cases - len(failures),
        "failures": failures,
        "passed": not failures,
        "limitations": "Generated color/shape patterns are not an independent recognition benchmark or a real-camera test.",
    }
    output = ROOT / "artifacts/sign_synthetic_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
