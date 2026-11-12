"""Small locally trained HOG/color softmax model; no heavyweight inference runtime."""

from pathlib import Path

import cv2
import numpy as np

LABELS = ("green_light", "red_light", "left", "right", "background")


class SignFeatures:
    def __init__(self):
        self.hog = cv2.HOGDescriptor((48, 48), (16, 16), (8, 8), (8, 8), 9)

    def compute(self, crop: np.ndarray) -> np.ndarray:
        image = cv2.resize(crop, (48, 48))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hog = self.hog.compute(gray).reshape(-1)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        histograms = [
            cv2.calcHist([hsv], [channel], None, [8], [0, limit]).reshape(-1) / (48 * 48)
            for channel, limit in ((0, 180), (1, 256), (2, 256))
        ]
        spatial = cv2.resize(image, (4, 4)).astype(np.float32).reshape(-1) / 255
        return np.concatenate([hog, *histograms, spatial]).astype(np.float32)


class SignClassifier:
    def __init__(self, model_path: str | Path):
        with np.load(model_path, allow_pickle=False) as data:
            self.weights = data["weights"].copy()
            self.bias = data["bias"].copy()
            self.mean = data["mean"].copy()
            self.scale = data["scale"].copy()
        self.features = SignFeatures()

    def classify(self, crop: np.ndarray) -> tuple[str, float]:
        feature = self.features.compute(crop)
        logits = ((feature - self.mean) / self.scale) @ self.weights + self.bias
        scores = np.exp(np.clip(logits - logits.max(), -80, 0))
        scores /= scores.sum()
        index = int(scores.argmax())
        return LABELS[index], float(scores[index])
