from pathlib import Path

import cv2
import numpy as np
import pytest
from rover_autonomy.types import Sign, Vision
from rover_autonomy.vision.hands import PalmDetector, palm_anchors
from rover_autonomy.vision.line import LineDetector
from rover_autonomy.vision.pipeline import PerceptionPipeline
from rover_autonomy.vision.signs import SignDetector

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("x,sign", [(60, -1), (160, 0), (260, 1)])
def test_line_position(x, sign):
    frame = np.full((240, 320, 3), 230, np.uint8)
    cv2.line(frame, (x, 239), (x, 130), (0, 0, 0), 16)
    value = LineDetector().detect(frame)
    assert value.confidence > 0.8
    assert abs(value.error) < 0.03 if sign == 0 else value.error * sign > 0.2


def test_no_line_and_upper_dark_object():
    frame = np.full((240, 320, 3), 230, np.uint8)
    frame[:100, 100:200] = 0
    assert LineDetector().detect(frame).confidence == 0


def test_anchor_layout_and_blank_hand_inference():
    anchors = palm_anchors()
    assert anchors.shape == (2016, 2)
    assert np.all((anchors > 0) & (anchors < 1))
    detector = PalmDetector(ROOT / "src/rover_autonomy/models/palm_detection_mediapipe_2023feb.onnx")
    try:
        assert detector.detect(np.zeros((240, 320, 3), np.uint8)) is None
    finally:
        detector.close()
    with pytest.raises(RuntimeError):
        detector.detect(np.zeros((240, 320, 3), np.uint8))


def test_pipeline_outputs_metadata_not_images():
    pipeline = PerceptionPipeline()
    frame = np.full((240, 320, 3), 230, np.uint8)
    value = pipeline.process(frame, 4, 10)
    assert isinstance(value, Vision)
    assert value.width == 320 and value.height == 240
    assert value.signs == () and value.hand is None
    with pytest.raises(RuntimeError):
        pipeline.process(frame, 5, 11, hand_enabled=True)
    pipeline.close()


def test_pretrained_palm_model_detects_the_licensed_reference_image():
    frame = cv2.imdecode(
        np.fromfile(ROOT / "tests/assets/palm_reference.png", dtype=np.uint8), cv2.IMREAD_COLOR
    )
    detector = PalmDetector(ROOT / "src/rover_autonomy/models/palm_detection_mediapipe_2023feb.onnx")
    try:
        hand = detector.detect(frame)
        assert hand is not None and hand.confidence > 0.65
        assert 0 < hand.area < 1
        assert hand.distance_m is None
    finally:
        detector.close()


def test_near_palm_padding_maps_area_back_to_original_frame_for_stop():
    reference = cv2.imdecode(
        np.fromfile(ROOT / "tests/assets/palm_reference.png", dtype=np.uint8), cv2.IMREAD_COLOR
    )
    near = cv2.resize(reference[150:450, 250:550], (320, 240))
    detector = PalmDetector(ROOT / "src/rover_autonomy/models/palm_detection_mediapipe_2023feb.onnx")
    try:
        hand = detector.detect(near)
        assert hand is not None and hand.confidence > 0.65
        assert hand.area > 0.075
    finally:
        detector.close()


@pytest.mark.parametrize("label", ["green_light", "red_light", "left", "right"])
def test_synthetic_sign_contract_without_a_trained_model(label):
    crop = cv2.imdecode(np.fromfile(ROOT / f"tests/assets/sign_{label}.png", np.uint8), 1)
    canvas = np.full((240, 320, 3), 225, np.uint8)
    scaled = cv2.resize(crop, (80, 120))
    canvas[20:140, 120:200] = scaled
    detector = SignDetector()
    assert detector.classifier is None
    assert any(item.label == Sign(label) for item in detector.detect(canvas))


def test_blue_circle_without_arrow_is_unknown():
    canvas = np.full((240, 320, 3), 225, np.uint8)
    cv2.circle(canvas, (160, 80), 60, (225, 80, 10), -1)
    assert SignDetector().detect(canvas) == ()


def test_experimental_classifier_cannot_load_without_an_explicit_path():
    with pytest.raises(ValueError):
        SignDetector(use_classifier=True)


def test_closed_pipeline_cannot_process_a_frame_again():
    pipeline = PerceptionPipeline()
    pipeline.close()
    with pytest.raises(RuntimeError, match="closed"):
        pipeline.process(np.zeros((240, 320, 3), np.uint8), 1, 1)


def test_pipeline_releases_ownership_even_if_model_cleanup_raises():
    class BrokenPalm:
        closes = 0

        def close(self):
            self.closes += 1
            raise RuntimeError("model cleanup failed")

    palm = BrokenPalm()
    pipeline = PerceptionPipeline(palm=palm)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        pipeline.close()
    pipeline.close()
    assert palm.closes == 1
    assert pipeline.palm is None


def test_pipeline_initialization_failure_releases_the_transferred_model():
    class Palm:
        closed = False

        def close(self):
            self.closed = True

    palm = Palm()
    with pytest.raises(ValueError, match="backend"):
        PerceptionPipeline(palm=palm, sign_backend="invalid")
    assert palm.closed
