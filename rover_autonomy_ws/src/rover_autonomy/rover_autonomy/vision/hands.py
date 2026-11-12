"""OpenCV DNN palm detection with generated SSD anchors and bounded NMS.

Model/decoding specification: OpenCV Zoo palm_detection_mediapipe, Apache-2.0.
Implementation changes: generated anchors, xywh NMS, clipped logits/boxes and one
selected target. See THIRD_PARTY_NOTICES.md and bundled model license.
"""

from pathlib import Path

import cv2
import numpy as np

from rover_autonomy.types import Hand


def palm_anchors() -> np.ndarray:
    return np.asarray(
        [
            ((x + 0.5) / grid, (y + 0.5) / grid)
            for grid, repetitions in ((24, 2), (12, 6))
            for y in range(grid)
            for x in range(grid)
            for _ in range(repetitions)
        ],
        dtype=np.float32,
    )


class PalmDetector:
    def __init__(
        self,
        model_path: str | Path,
        confidence: float = 0.65,
        calibrated_fx: float = 0.0,
        calibrated_image_width: int = 640,
        palm_width_m: float = 0.0,
    ):
        if not Path(model_path).is_file():
            raise FileNotFoundError(f"Palm model missing: {model_path}; run scripts/fetch_models.py")
        # Loading ONNX from bytes also supports Windows workspaces with Korean paths.
        self.net = cv2.dnn.readNetFromONNX(np.frombuffer(Path(model_path).read_bytes(), np.uint8))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        self.anchors = palm_anchors()
        self.confidence = confidence
        self.fx = calibrated_fx
        self.calibration_width = calibrated_image_width
        self.palm_width_m = palm_width_m
        self.last_center = None
        self.inference_count = 0

    def detect(self, frame: np.ndarray, *, _allow_padding: bool = True) -> Hand | None:
        if self.net is None:
            raise RuntimeError("Palm detector is closed")
        height, width = frame.shape[:2]
        ratio = 192 / max(width, height)
        resized_w, resized_h = round(width * ratio), round(height * ratio)
        small = cv2.resize(frame, (resized_w, resized_h))
        left, top = (192 - resized_w) // 2, (192 - resized_h) // 2
        small = cv2.copyMakeBorder(
            small, top, 192 - resized_h - top, left, 192 - resized_w - left, cv2.BORDER_CONSTANT
        )
        tensor = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32)[None] / 255
        self.net.setInput(tensor)
        self.inference_count += 1
        outputs = self.net.forward(self.net.getUnconnectedOutLayersNames())
        boxes_raw = next(value for value in outputs if value.shape[-1] == 18)[0, :, :4]
        scores_raw = next(value for value in outputs if value.shape[-1] == 1)[0, :, 0]
        if len(boxes_raw) != len(self.anchors):
            raise ValueError("Unsupported palm model anchor count")
        scores = 1 / (1 + np.exp(-np.clip(scores_raw, -60, 60)))
        indices = np.flatnonzero(scores >= self.confidence)
        if not len(indices):
            return self._no_target(frame, _allow_padding)
        centers = (boxes_raw[indices, :2] / 192 + self.anchors[indices]) * 192
        sizes = boxes_raw[indices, 2:4]
        xy1 = (centers - sizes / 2 - np.asarray([left, top])) / ratio
        xy2 = (centers + sizes / 2 - np.asarray([left, top])) / ratio
        xy1 = np.maximum(xy1, 0)
        xy2 = np.minimum(xy2, [width, height])
        boxes = np.c_[xy1, xy2 - xy1]
        good = (boxes[:, 2] > 2) & (boxes[:, 3] > 2)
        boxes, indices = boxes[good], indices[good]
        if not len(indices):
            return self._no_target(frame, _allow_padding)
        keep = cv2.dnn.NMSBoxes(boxes.tolist(), scores[indices].tolist(), self.confidence, 0.3, top_k=20)
        if not len(keep):
            return self._no_target(frame, _allow_padding)
        candidates = []
        for index in np.asarray(keep).reshape(-1):
            x, y, w, h = boxes[index]
            cx = (x + w / 2) / width * 2 - 1
            area = float(w * h / (width * height))
            score = float(scores[indices[index]])
            continuity = 0 if self.last_center is None else abs(cx - self.last_center) * 0.2
            candidates.append((score + min(area, 0.2) - continuity, cx, area, score, (x, y, w, h)))
        _, cx, area, score, box = max(candidates, key=lambda item: item[0])
        self.last_center = cx
        distance = None
        if self.fx > 0 and self.palm_width_m > 0 and self.calibration_width > 0:
            distance = float(self.fx * width / self.calibration_width * self.palm_width_m / box[2])
        return Hand(float(cx), area, score, tuple(int(value) for value in box), distance)

    def _no_target(self, frame, allow_padding):
        self.last_center = None
        if not allow_padding:
            return None
        # SSD can miss a large near-camera hand despite a visible palm. One bounded
        # padded pass restores context; map the result back before testing stop area.
        height, width = frame.shape[:2]
        pad = max(height, width) // 8
        padded = cv2.copyMakeBorder(frame, pad, pad, pad, pad, cv2.BORDER_CONSTANT)
        value = self.detect(padded, _allow_padding=False)
        if value is None:
            return None
        x, y, w, h = value.box
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(width, x + w - pad), min(height, y + h - pad)
        if x2 - x1 <= 2 or y2 - y1 <= 2:
            self.last_center = None
            return None
        cx = ((x1 + x2) / 2) / width * 2 - 1
        self.last_center = cx
        area = (x2 - x1) * (y2 - y1) / (width * height)
        distance = None
        if self.fx > 0 and self.palm_width_m > 0 and self.calibration_width > 0:
            distance = self.fx * width / self.calibration_width * self.palm_width_m / (x2 - x1)
        return Hand(cx, area, value.confidence, (x1, y1, x2 - x1, y2 - y1), distance)

    def close(self):
        self.net = None
        self.last_center = None
