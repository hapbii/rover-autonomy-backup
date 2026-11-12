from dataclasses import dataclass

import cv2
import numpy as np

from rover_autonomy.types import Line


@dataclass(frozen=True, slots=True)
class LineConfig:
    roi_top: float = 0.58
    dark_line: bool = True
    threshold: int = 75
    min_area_fraction: float = 0.003
    max_area_fraction: float = 0.38

    def __post_init__(self):
        if not 0.1 <= self.roi_top <= 0.9:
            raise ValueError("Line ROI must leave at least 10% of the image")
        if (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, int)
            or not 0 <= self.threshold <= 255
        ):
            raise ValueError("Line threshold must be an integer from 0 to 255")
        if not 0 < self.min_area_fraction < self.max_area_fraction < 1:
            raise ValueError("Invalid line area limits")


class LineDetector:
    def __init__(self, config: LineConfig | None = None):
        self.config = config or LineConfig()
        self.kernel = np.ones((3, 3), np.uint8)

    def detect(self, frame: np.ndarray) -> Line:
        height, width = frame.shape[:2]
        top = int(height * self.config.roi_top)
        roi = frame[top:, :]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        mode = cv2.THRESH_BINARY_INV if self.config.dark_line else cv2.THRESH_BINARY
        _, mask = cv2.threshold(gray, self.config.threshold, 255, mode)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        roi_area = mask.size
        candidates = [
            contour
            for contour in contours
            if self.config.min_area_fraction
            <= cv2.contourArea(contour) / roi_area
            <= self.config.max_area_fraction
        ]
        if not candidates:
            return Line()
        # Prefer a track reaching the bottom of the view over dark objects farther ahead.
        contour = max(candidates, key=lambda item: cv2.boundingRect(item)[1] + cv2.boundingRect(item)[3])
        moments = cv2.moments(contour)
        if moments["m00"] <= 0:
            return Line()
        cx = moments["m10"] / moments["m00"]
        _, y, _, span = cv2.boundingRect(contour)
        vx, vy, _, _ = cv2.fitLine(contour, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
        heading = float(np.clip(vx / (abs(vy) + 1e-6), -1, 1))
        # A fitLine vector has arbitrary sign. Point its y component toward image bottom.
        if vy < 0:
            heading = -heading
        continuity = span / max(1, mask.shape[0])
        reaches_bottom = (y + span) / max(1, mask.shape[0])
        confidence = float(np.clip(0.65 * continuity + 0.35 * reaches_bottom, 0, 1))
        return Line(float(np.clip((cx - width / 2) / (width / 2), -1, 1)), confidence, heading)
