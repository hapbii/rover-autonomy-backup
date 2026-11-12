"""Versioned bounded JSON between ROS nodes; no images or histories in messages."""

import json
from dataclasses import asdict
from math import isfinite

from rover_autonomy.types import Detection, Hand, Line, Sign, Vision

MAX_MESSAGE_BYTES = 8192


def number(value, minimum=-1e10, maximum=1e10):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError("Invalid numeric field")
    return value


def box(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("Invalid box")
    result = tuple(int(number(item, 0, 3840)) for item in value)
    if result[2] <= 0 or result[3] <= 0:
        raise ValueError("Empty box")
    return result


def encode_vision(value: Vision, now: float, stamp_ns: int = 0) -> str:
    payload = {
        "version": 1,
        "sequence": value.sequence,
        "stream_id": value.stream_id,
        "age": max(0.0, now - value.captured_at),
        "stamp_ns": stamp_ns,
        "width": value.width,
        "height": value.height,
        "line": asdict(value.line),
        "signs": [asdict(item) for item in value.signs[:8]],
        "hand": asdict(value.hand) if value.hand is not None else None,
    }
    result = json.dumps(payload, separators=(",", ":"), allow_nan=False)
    if len(result.encode()) > MAX_MESSAGE_BYTES:
        raise ValueError("Vision packet too large")
    return result


def decode_vision(text: str, now: float, ros_now_ns: int | None = None) -> Vision:
    if len(text.encode()) > MAX_MESSAGE_BYTES:
        raise ValueError("Vision packet too large")
    value = json.loads(text)
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Unsupported vision message")
    sequence = int(number(value["sequence"], 0, 2**53))
    width, height = int(number(value["width"], 1, 3840)), int(number(value["height"], 1, 2160))
    age = number(value["age"], 0, 10)
    stamp = int(number(value.get("stamp_ns", 0), 0, 2**64))
    if ros_now_ns is not None and stamp:
        age = number((ros_now_ns - stamp) / 1e9, 0, 10)
    stream_id = value.get("stream_id", "")
    if not isinstance(stream_id, str) or len(stream_id) > 64:
        raise ValueError("Invalid camera stream identifier")
    raw_line = value["line"]
    line = Line(
        number(raw_line["error"], -1, 1),
        number(raw_line["confidence"], 0, 1),
        number(raw_line["heading"], -1, 1),
    )
    raw_signs = value["signs"]
    if not isinstance(raw_signs, list) or len(raw_signs) > 8:
        raise ValueError("Too many signs")
    signs = tuple(
        Detection(Sign(item["label"]), number(item["confidence"], 0, 1), box(item["box"]))
        for item in raw_signs
    )
    hand = None
    raw_hand = value["hand"]
    if raw_hand is not None:
        distance = raw_hand["distance_m"]
        if distance is not None:
            distance = number(distance, 0.01, 20)
        hand = Hand(
            number(raw_hand["center_x"], -1, 1),
            number(raw_hand["area"], 0.000001, 1),
            number(raw_hand["confidence"], 0, 1),
            box(raw_hand["box"]),
            distance,
        )
    return Vision(sequence, now - age, line, signs, hand, width, height, stream_id)
