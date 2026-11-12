"""ROS Image decoding without cv_bridge ABI dependencies."""

import cv2
import numpy as np


def decode_raw_image(data, width: int, height: int, step: int, encoding: str):
    if not 32 <= width <= 1280 or not 32 <= height <= 960:
        raise ValueError("Raw frame exceeds camera limits")
    channels = 1 if encoding == "mono8" else 3 if encoding in ("bgr8", "rgb8") else 0
    if not channels or not width * channels <= step <= width * channels + 4096:
        raise ValueError("Unsupported image encoding/stride")
    if len(data) != height * step or len(data) > 4_000_000:
        raise ValueError("Malformed raw image size")
    rows = np.frombuffer(data, np.uint8).reshape(height, step)
    pixels = rows[:, : width * channels].reshape(height, width, channels)
    if encoding == "rgb8":
        return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    if encoding == "mono8":
        return cv2.cvtColor(pixels, cv2.COLOR_GRAY2BGR)
    return pixels
