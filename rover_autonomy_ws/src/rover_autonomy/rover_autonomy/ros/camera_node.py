import cv2
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage

from rover_autonomy.hardware.camera import ImageCamera, OpenCVCamera, PiCamera
from rover_autonomy.ros.common import configuration, sensor_qos, spin_main


class CameraNode(Node):
    def __init__(self):
        super().__init__("rover_camera")
        self.source = None
        config, _ = configuration(self)
        settings = config.get("camera", {})
        backend = self.declare_parameter("backend", settings.get("backend", "picamera2")).value
        self.rotate = bool(settings.get("rotate_180", False))
        fps = float(settings.get("fps", 12))
        if not 1 <= fps <= 30:
            raise ValueError("Camera FPS must be between 1 and 30")
        width, height = int(settings.get("width", 640)), int(settings.get("height", 480))
        if not 160 <= width <= 1280 or not 120 <= height <= 960:
            raise ValueError("Camera dimensions outside configured limits")
        self.publisher = self.create_publisher(CompressedImage, "/rover/camera/compressed", sensor_qos())
        try:
            if backend == "picamera2":
                self.source = PiCamera(width, height, fps)
            elif backend == "opencv":
                self.source = OpenCVCamera(settings.get("source", 0), width, height, fps)
            elif backend == "image":
                self.source = ImageCamera(settings.get("source", ""))
            else:
                raise ValueError(f"Unknown camera backend: {backend}")
            self.create_timer(1 / fps, self.tick)
        except BaseException:
            self.destroy_node()
            raise

    def tick(self):
        try:
            frame = self.source.read()
            stamp = self.get_clock().now().to_msg()
            if self.rotate:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            success, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not success:
                raise RuntimeError("JPEG encoding failed")
            message = CompressedImage()
            message.header.stamp = stamp
            message.header.frame_id = "rover_camera"
            message.format = "jpeg"
            message.data = encoded.tobytes()
            self.publisher.publish(message)
        except (RuntimeError, cv2.error) as error:
            self.get_logger().error(str(error), throttle_duration_sec=2.0)

    def destroy_node(self):
        source, self.source = self.source, None
        try:
            if source is not None:
                source.close()
        finally:
            result = super().destroy_node()
        return result


def main(args=None):
    spin_main(CameraNode, args)
