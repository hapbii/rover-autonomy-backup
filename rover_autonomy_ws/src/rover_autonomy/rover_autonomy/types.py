"""Small immutable messages shared by offline tests and ROS adapters."""

from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite


class Mode(StrEnum):
    IDLE = "idle"
    AUTONOMOUS = "autonomous"
    LINE = "line"
    HAND = "hand"


class Sign(StrEnum):
    NONE = "none"
    GREEN = "green_light"
    RED = "red_light"
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True, slots=True)
class Line:
    error: float = 0.0
    confidence: float = 0.0
    heading: float = 0.0


@dataclass(frozen=True, slots=True)
class Detection:
    label: Sign
    confidence: float
    # Pixel coordinates x, y, width, height. Never store an image in observations.
    box: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class Hand:
    center_x: float  # normalized -1 (image left) to +1 (image right)
    area: float  # palm box area / image area
    confidence: float
    box: tuple[int, int, int, int]
    distance_m: float | None = None  # Only available with explicit camera/palm calibration.


@dataclass(frozen=True, slots=True)
class Vision:
    sequence: int
    captured_at: float
    line: Line = field(default_factory=Line)
    signs: tuple[Detection, ...] = ()
    hand: Hand | None = None
    width: int = 0
    height: int = 0
    stream_id: str = ""


@dataclass(frozen=True, slots=True)
class Range:
    distance_m: float
    sampled_at: float

    def valid(self, now: float, timeout: float) -> bool:
        return (
            isfinite(self.distance_m)
            and 0.02 <= self.distance_m <= 4.0
            and 0.0 <= now - self.sampled_at <= timeout
        )


@dataclass(frozen=True, slots=True)
class Odometry:
    x: float
    y: float
    yaw: float
    sampled_at: float


@dataclass(frozen=True, slots=True)
class Command:
    linear: float = 0.0
    angular: float = 0.0
    reason: str = "idle"

    @property
    def stopped(self) -> bool:
        return self.linear == 0.0 and self.angular == 0.0
