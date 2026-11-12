"""Explicit camera ownership, Unicode-safe file inputs and deterministic release."""

from pathlib import Path

import cv2
import numpy as np


class OpenCVCamera:
    def __init__(self, source=0, width=640, height=480, fps=12):
        self.capture = None
        self.closed = False
        try:
            if isinstance(source, (str, Path)) and Path(source).is_file():
                # The general OpenCV worker limit does not limit FFmpeg codecs.
                # CAP_PROP_N_THREADS is open-only; bound file decoding separately.
                self.capture = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
            else:
                self.capture = cv2.VideoCapture(source)
            if not self.capture.isOpened():
                raise RuntimeError(f"Cannot open camera/video source {source}")
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.capture.set(cv2.CAP_PROP_FPS, fps)
            self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except BaseException:
            self.close()
            raise

    def read(self):
        if self.closed:
            raise RuntimeError("Camera is closed")
        success, image = self.capture.read()
        if not success or image is None:
            raise RuntimeError("Camera/video frame unavailable")
        return image

    def close(self):
        if not self.closed:
            self.closed = True
            capture, self.capture = self.capture, None
            if capture is not None:
                capture.release()


class PiCamera:
    def __init__(self, width=640, height=480, fps=12, camera_factory=None):
        if camera_factory is None:
            from picamera2 import Picamera2

            camera_factory = Picamera2
        self.camera = camera_factory()
        self.closed = False
        try:
            # Picamera2's packed RGB888 produces BGR bytes for OpenCV on Pi.
            config = self.camera.create_video_configuration(
                main={"size": (width, height), "format": "RGB888"},
                controls={"FrameRate": fps},
                buffer_count=4,
            )
            self.camera.configure(config)
            self.camera.start()
        except BaseException:
            self.close()
            raise

    def read(self):
        if self.closed:
            raise RuntimeError("Pi camera is closed")
        request = self.camera.capture_request()
        try:
            # Copy before releasing libcamera's buffer. Never retain a Request object.
            return request.make_array("main").copy()
        finally:
            request.release()

    def close(self):
        if self.closed:
            return
        self.closed = True
        camera, self.camera = self.camera, None
        try:
            camera.stop()
        finally:
            camera.close()


class ImageCamera:
    """A still image repeatedly sampled for local ROS bringup; not real-time motion input."""

    def __init__(self, path):
        self.image = cv2.imdecode(np.fromfile(Path(path), np.uint8), cv2.IMREAD_COLOR)
        if self.image is None:
            raise ValueError("Image source could not be decoded")

    def read(self):
        if self.image is None:
            raise RuntimeError("Image source is closed")
        return self.image.copy()

    def close(self):
        self.image = None
