import signal
from contextlib import contextmanager
from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.executors import ExternalShutdownException
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

from rover_autonomy.config import load_configuration


def sensor_qos():
    return QoSProfile(
        history=HistoryPolicy.KEEP_LAST,
        depth=1,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE,
    )


def state_qos():
    return QoSProfile(
        depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL
    )


def configuration(node):
    share = Path(get_package_share_directory("rover_autonomy"))
    path = node.declare_parameter("config_path", str(share / "config/rover.yaml")).value
    return load_configuration(path), share


@contextmanager
def cleanup_signals():
    """A second launch/terminal signal must not interrupt native resource cleanup."""
    previous = {}
    try:
        for value in (signal.SIGINT, signal.SIGTERM):
            previous[value] = signal.signal(value, signal.SIG_IGN)
        yield
    finally:
        for value, handler in previous.items():
            signal.signal(value, handler)


def spin_main(factory, args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = factory()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        with cleanup_signals():
            try:
                if node is not None:
                    node.destroy_node()
            finally:
                if rclpy.ok():
                    rclpy.shutdown()
