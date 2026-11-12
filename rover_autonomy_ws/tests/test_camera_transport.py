import json

import cv2
import numpy as np
import pytest
from rover_autonomy.hardware.camera import OpenCVCamera, PiCamera
from rover_autonomy.hardware.images import decode_raw_image
from rover_autonomy.transport import decode_vision, encode_vision
from rover_autonomy.types import Hand, Line, Vision


class Request:
    active = 0

    def __init__(self, fail=False):
        self.image = np.ones((20, 20, 3), np.uint8)
        self.fail = fail
        Request.active += 1

    def make_array(self, _):
        if self.fail:
            raise RuntimeError("simulated capture failure")
        return self.image

    def release(self):
        self.image[:] = 0
        Request.active -= 1


class FakePi:
    def __init__(self):
        self.fail = False
        self.stopped = self.closed = False

    def create_video_configuration(self, **_):
        return {}

    def configure(self, _):
        pass

    def start(self):
        pass

    def capture_request(self):
        return Request(self.fail)

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True


def test_camera_request_is_released_and_frame_owns_its_memory():
    device = FakePi()
    camera = PiCamera(camera_factory=lambda: device)
    for _ in range(100):
        frame = camera.read()
        assert Request.active == 0
        assert np.all(frame == 1)
    camera.close()
    camera.close()
    assert device.stopped and device.closed


def test_capture_failure_still_releases_request():
    device = FakePi()
    device.fail = True
    camera = PiCamera(camera_factory=lambda: device)
    with pytest.raises(RuntimeError):
        camera.read()
    assert Request.active == 0
    camera.close()


def test_stop_failure_still_closes_camera():
    device = FakePi()
    camera = PiCamera(camera_factory=lambda: device)

    def bad_stop():
        raise RuntimeError("camera unplugged")

    device.stop = bad_stop
    with pytest.raises(RuntimeError):
        camera.close()
    assert camera.closed and device.closed
    camera.close()


class FakeCapture:
    def __init__(self, *, fail_set=False, fail_release=False):
        self.fail_set = fail_set
        self.fail_release = fail_release
        self.releases = 0

    def isOpened(self):
        return True

    def set(self, *_):
        if self.fail_set:
            raise RuntimeError("device disconnected during configuration")

    def release(self):
        self.releases += 1
        if self.fail_release:
            raise RuntimeError("decoder release failed")


def test_opencv_configuration_failure_releases_already_open_device(monkeypatch):
    device = FakeCapture(fail_set=True)
    monkeypatch.setattr("rover_autonomy.hardware.camera.cv2.VideoCapture", lambda _: device)
    with pytest.raises(RuntimeError, match="configuration"):
        OpenCVCamera()
    assert device.releases == 1


def test_failed_opencv_close_does_not_retain_or_release_device_twice(monkeypatch):
    device = FakeCapture(fail_release=True)
    monkeypatch.setattr("rover_autonomy.hardware.camera.cv2.VideoCapture", lambda _: device)
    camera = OpenCVCamera()
    with pytest.raises(RuntimeError, match="release failed"):
        camera.close()
    camera.close()
    assert device.releases == 1
    assert camera.capture is None
    with pytest.raises(RuntimeError, match="closed"):
        camera.read()


def test_closed_pi_camera_drops_native_device_reference():
    device = FakePi()
    camera = PiCamera(camera_factory=lambda: device)
    camera.close()
    assert camera.camera is None


def test_file_decoder_limits_codec_threads_when_opening(monkeypatch, tmp_path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fake file; capture is injected")
    arguments = []
    device = FakeCapture()

    def open_capture(*args):
        arguments.append(args)
        return device

    monkeypatch.setattr("rover_autonomy.hardware.camera.cv2.VideoCapture", open_capture)
    camera = OpenCVCamera(video)
    camera.close()
    assert arguments == [(str(video), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])]
    assert device.releases == 1


def test_vision_roundtrip_accounts_for_ros_capture_age():
    value = Vision(
        2,
        10,
        Line(0.1, 0.8),
        hand=Hand(-0.2, 0.03, 0.9, (10, 10, 30, 30)),
        width=320,
        height=240,
        stream_id="camera_boot",
    )
    text = encode_vision(value, 10.1, 1000000000)
    decoded = decode_vision(text, 10.3, 1300000000)
    assert decoded.captured_at == pytest.approx(10)
    assert decoded.hand == value.hand
    assert decoded.stream_id == "camera_boot"


@pytest.mark.parametrize("bad", ["x" * 9000, "{", '{"version": 2}', '{"version": 1, "sequence": NaN}'])
def test_invalid_vision_packets(bad):
    with pytest.raises((ValueError, KeyError, TypeError)):
        decode_vision(bad, 10)


def test_invalid_scores_and_too_many_detections():
    value = Vision(1, 10, Line(0, 0.9), width=320, height=240)
    packet = json.loads(encode_vision(value, 10))
    packet["line"]["confidence"] = float("nan")
    with pytest.raises(ValueError):
        decode_vision(json.dumps(packet), 10)


def test_raw_rgb_with_row_padding():
    rows = np.zeros((32, 100), np.uint8)
    rows[:, :96] = np.tile([255, 0, 0], 32)
    image = decode_raw_image(rows.tobytes(), 32, 32, 100, "rgb8")
    assert image.shape == (32, 32, 3)
    assert tuple(image[0, 0]) == (0, 0, 255)


@pytest.mark.parametrize(
    "data,width,height,step,encoding",
    [(b"", 32, 32, 96, "bgr8"), (b"x", 10000, 32, 30000, "bgr8"), (b"x", 32, 32, 96, "rgba8")],
)
def test_malformed_raw_frames(data, width, height, step, encoding):
    with pytest.raises(ValueError):
        decode_raw_image(data, width, height, step, encoding)
