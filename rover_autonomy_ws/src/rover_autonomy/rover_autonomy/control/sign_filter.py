from collections import deque
from math import isfinite

from rover_autonomy.types import Detection, Sign


class SignFilter:
    def __init__(self, confirmations: int, confidence: float):
        self.history = deque(maxlen=confirmations)
        self.confidence = confidence
        self.last_sequence = -1
        self.red_latched = False
        self.confirmed = Sign.NONE

    def observe(self, sequence: int, signs: tuple[Detection, ...]):
        if sequence <= self.last_sequence:
            return
        self.last_sequence = sequence
        labels = {
            item.label
            for item in signs[:8]
            if isfinite(item.confidence) and self.confidence <= item.confidence <= 1
        }
        if Sign.RED in labels:
            # Red wins even if a green object is also visible.
            self.red_latched = True
            label = Sign.RED
        elif Sign.GREEN in labels:
            label = Sign.GREEN
        elif Sign.LEFT in labels and Sign.RIGHT not in labels:
            label = Sign.LEFT
        elif Sign.RIGHT in labels and Sign.LEFT not in labels:
            label = Sign.RIGHT
        else:
            label = Sign.NONE
        self.history.append(label)
        if len(self.history) == self.history.maxlen and all(value == label for value in self.history):
            self.confirmed = label
            if label == Sign.GREEN:
                self.red_latched = False
        else:
            self.confirmed = Sign.NONE
