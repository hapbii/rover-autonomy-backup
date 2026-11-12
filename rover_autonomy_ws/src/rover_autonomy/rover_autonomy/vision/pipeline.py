import cv2
import numpy as np

from rover_autonomy.types import Vision
from rover_autonomy.vision.hands import PalmDetector
from rover_autonomy.vision.line import LineConfig, LineDetector
from rover_autonomy.vision.signs import SignDetector


class PerceptionPipeline:
    def __init__(
        self,
        line_config: LineConfig | None = None,
        palm: PalmDetector | None = None,
        sign_model_path=None,
        sign_backend: str = "geometry",
    ):
        self.palm = palm
        self.closed = False
        try:
            cv2.setNumThreads(1)
            self.line = LineDetector(line_config)
            if sign_backend not in ("geometry", "experimental_hog"):
                raise ValueError("Unknown sign backend")
            self.signs = SignDetector(
                model_path=sign_model_path, use_classifier=sign_backend == "experimental_hog"
            )
        except BaseException:
            self.close()
            raise

    def process(
        self, frame: np.ndarray, sequence: int, captured_at: float, hand_enabled: bool = False
    ) -> Vision:
        if self.closed:
            raise RuntimeError("Perception pipeline is closed")
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("Expected an 8-bit three-channel BGR image")
        if not 32 <= frame.shape[0] <= 2160 or not 32 <= frame.shape[1] <= 3840:
            raise ValueError("Unsupported frame dimensions")
        if frame.shape[1] > 640:
            frame = cv2.resize(frame, (640, round(frame.shape[0] * 640 / frame.shape[1])))
        if hand_enabled and self.palm is None:
            raise RuntimeError("Hand mode requires the palm detector model")
        return Vision(
            sequence=sequence,
            captured_at=captured_at,
            line=self.line.detect(frame),
            signs=self.signs.detect(frame),
            hand=self.palm.detect(frame) if hand_enabled and self.palm is not None else None,
            width=frame.shape[1],
            height=frame.shape[0],
        )

    def close(self):
        if self.closed:
            return
        self.closed = True
        palm, self.palm = self.palm, None
        if palm is not None:
            palm.close()
