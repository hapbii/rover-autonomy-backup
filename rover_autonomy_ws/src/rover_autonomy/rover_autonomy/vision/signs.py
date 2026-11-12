"""Default: untrained HSV/circle/arrow geometry recognizer for course prototypes.

No project-specific sign photographs have been supplied or validated. The optional
HOG classifier is experimental and requires an explicitly provided model path.
Synthetic regression tests are not measurements of real-camera accuracy.
"""

from math import pi
from pathlib import Path

import cv2
import numpy as np

from rover_autonomy.types import Detection, Sign
from rover_autonomy.vision.sign_classifier import SignClassifier


class SignDetector:
    def __init__(
        self,
        min_area: float = 0.00025,
        max_area: float = 0.45,
        max_detections: int = 8,
        model_path: str | Path | None = None,
        use_classifier: bool = False,
    ):
        self.min_area = min_area
        self.max_area = max_area
        self.max_detections = max_detections
        self.kernel = np.ones((3, 3), np.uint8)
        if use_classifier and model_path is None:
            raise ValueError("Experimental sign classification requires an explicit model_path")
        self.classifier = SignClassifier(Path(model_path)) if use_classifier else None

    def detect(self, frame: np.ndarray) -> tuple[Detection, ...]:
        height, width = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        dark = cv2.inRange(hsv, (0, 0, 0), (179, 255, 125))
        dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
        dark_contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dark_boxes = [cv2.boundingRect(item) for item in dark_contours if cv2.contourArea(item) > 100]
        masks = (
            (
                Sign.RED,
                cv2.inRange(hsv, (0, 100, 65), (12, 255, 255))
                | cv2.inRange(hsv, (168, 100, 65), (179, 255, 255)),
            ),
            (Sign.GREEN, cv2.inRange(hsv, (35, 165, 50), (90, 255, 255))),
            (Sign.NONE, cv2.inRange(hsv, (90, 130, 40), (138, 255, 255))),
        )
        detections = []
        image_area = height * width
        for label, mask in masks:
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            # Keep work bounded even in a noisy textured image.
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:16]
            for contour in contours:
                area = cv2.contourArea(contour)
                if not self.min_area <= area / image_area <= self.max_area:
                    continue
                x, y, w, h = cv2.boundingRect(contour)
                if y + h / 2 > height * 0.85 or not 0.55 <= w / max(1, h) <= 1.65:
                    continue
                perimeter = cv2.arcLength(contour, True)
                circularity = 4 * pi * area / max(perimeter * perimeter, 1)
                geometry_min = 0.35 if label == Sign.NONE else 0.60
                if circularity < (0.12 if self.classifier else geometry_min):
                    continue
                if self.classifier is not None:
                    proposals = (
                        [
                            (
                                round(x - w * margin),
                                round(y - h * margin),
                                round(w * (1 + 2 * margin)),
                                round(h * (1 + 2 * margin)),
                            )
                            for margin in (0, 0.04, 0.08, 0.12)
                        ]
                        if label == Sign.NONE
                        else self._light_proposals(x, y, w, h, label, dark_boxes)
                    )
                    for px, py, pw, ph in proposals[:5]:
                        x1, y1, x2, y2 = max(0, px), max(0, py), min(width, px + pw), min(height, py + ph)
                        if x2 <= x1 or y2 <= y1:
                            continue
                        predicted, score = self.classifier.classify(frame[y1:y2, x1:x2])
                        allowed = (
                            (Sign.LEFT.value, Sign.RIGHT.value) if label == Sign.NONE else (label.value,)
                        )
                        if predicted in allowed and score >= 0.80:
                            detections.append(Detection(Sign(predicted), score, (x1, y1, x2 - x1, y2 - y1)))
                    continue
                if label == Sign.NONE:
                    arrow, confidence = self._arrow(frame[y : y + h, x : x + w])
                    if arrow == Sign.NONE:
                        continue
                    detections.append(Detection(arrow, confidence, (x, y, w, h)))
                else:
                    confidence = min(0.99, 0.65 + 0.35 * circularity)
                    proposals = self._light_proposals(x, y, w, h, label, dark_boxes)
                    housing = proposals[0] if len(proposals) > 1 else (x, y, w, h)
                    detections.append(Detection(label, confidence, housing))
        # Different colored fragments may propose the same sign; retain one box.
        detections.sort(
            key=lambda item: (item.label == Sign.RED, item.confidence, item.box[2] * item.box[3]),
            reverse=True,
        )
        selected = []
        for item in detections:
            if any(item.label == kept.label and self._iou(item.box, kept.box) > 0.35 for kept in selected):
                continue
            selected.append(item)
            if len(selected) == self.max_detections:
                break
        return tuple(selected)

    @staticmethod
    def _light_proposals(x, y, w, h, label, dark_boxes):
        candidates = [
            (bx, by, bw, bh)
            for bx, by, bw, bh in dark_boxes
            if bx <= x + w / 2 <= bx + bw
            and by <= y + h / 2 <= by + bh
            and 1.2 <= bw / w <= 5
            and 1.5 <= bh / h <= 6
            and 0.25 <= bw / bh <= 1.1
        ]
        candidates.sort(key=lambda box: box[2] * box[3])
        offset = 1.8 if label == Sign.GREEN else 0.2
        candidates.append((round(x - w * 0.5), round(y - h * offset), round(w * 2), round(h * 3)))
        return candidates

    @staticmethod
    def _iou(a, b):
        intersection = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(
            0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
        )
        return intersection / max(1, a[2] * a[3] + b[2] * b[3] - intersection)

    @staticmethod
    def _arrow(crop: np.ndarray) -> tuple[Sign, float]:
        h, w = crop.shape[:2]
        # Rectify the circular sign's simple elliptical foreshortening before
        # comparing the arrow's horizontal edge profiles.
        if h != w:
            size = max(h, w)
            crop = cv2.resize(crop, (size, size))
            h, w = size, size
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        # Support black or white arrows on blue, excluding the outer circular rim.
        masks = (cv2.inRange(hsv, (0, 0, 0), (179, 170, 115)), cv2.inRange(hsv, (0, 0, 165), (179, 75, 255)))
        inside = np.zeros((h, w), np.uint8)
        cv2.ellipse(inside, (w // 2, h // 2), (int(w * 0.43), int(h * 0.43)), 0, 0, 360, 255, -1)
        candidates = []
        for mask in masks:
            mask &= inside
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                continue
            contour = max(contours, key=cv2.contourArea)
            if cv2.contourArea(contour) < 0.035 * w * h:
                continue
            polygon = cv2.approxPolyDP(contour, 0.022 * cv2.arcLength(contour, True), True).reshape(-1, 2)
            if not 5 <= len(polygon) <= 12:
                continue
            edges = np.roll(polygon, -1, axis=0) - polygon
            next_edges = np.roll(edges, -1, axis=0)
            crosses = edges[:, 0] * next_edges[:, 1] - edges[:, 1] * next_edges[:, 0]
            positive, negative = np.count_nonzero(crosses > 0), np.count_nonzero(crosses < 0)
            if min(positive, negative) < 2:
                continue  # A circle/triangle/rectangle is not an arrow.
            bx, by, bw, bh = cv2.boundingRect(contour)
            if bw < bh * 0.9:
                continue
            filled = np.zeros((bh, bw), np.uint8)
            shifted = contour - np.array([[[bx, by]]])
            cv2.drawContours(filled, [shifted], -1, 255, -1)
            strip = max(2, int(bw * 0.12))
            left_height = np.count_nonzero(filled[:, :strip]) / strip
            right_height = np.count_nonzero(filled[:, -strip:]) / strip
            contrast = (right_height - left_height) / bh
            if abs(contrast) < 0.09:
                continue
            label = Sign.LEFT if contrast > 0 else Sign.RIGHT
            candidates.append((label, min(0.99, 0.76 + abs(contrast))))
        return max(candidates, key=lambda item: item[1]) if candidates else (Sign.NONE, 0.0)
