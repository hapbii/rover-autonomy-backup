"""Small deterministic plane/sonar model for offline tests, never a hardware backend."""

from dataclasses import dataclass
from math import cos, sin, sqrt

import cv2
import numpy as np

from rover_autonomy.types import Command, Odometry


@dataclass(slots=True)
class World:
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    obstacle_x: float = 0.65
    obstacle_y: float = 0.0
    obstacle_radius: float = 0.12
    obstacle_enabled: bool = False

    def advance(self, command: Command, dt: float):
        self.x += command.linear * cos(self.yaw + command.angular * dt / 2) * dt
        self.y += command.linear * sin(self.yaw + command.angular * dt / 2) * dt
        self.yaw += command.angular * dt

    def odometry(self, now: float):
        return Odometry(self.x, self.y, self.yaw, now)

    def distance(self):
        if not self.obstacle_enabled:
            return 2.0
        ox, oy = self.x + 0.06 * cos(self.yaw), self.y + 0.06 * sin(self.yaw)
        dx, dy = self.obstacle_x - ox, self.obstacle_y - oy
        projection = dx * cos(self.yaw) + dy * sin(self.yaw)
        discriminant = self.obstacle_radius**2 - (dx * dx + dy * dy - projection * projection)
        if discriminant < 0 or projection <= 0:
            return 2.0
        distance = projection - sqrt(discriminant)
        return max(0.02, distance) if distance > 0 else 0.02

    def line_error(self):
        return float(np.clip(self.y * 2.5 + sin(self.yaw) * 0.85, -1, 1))

    def frame(self, width=320, height=240):
        frame = np.full((height, width, 3), 225, np.uint8)
        if abs(self.y) > 0.5:
            return frame
        error = self.line_error()
        bottom_x = round(width / 2 + error * width * 0.45)
        top_x = round(width / 2 + (error + 0.25 * sin(self.yaw)) * width * 0.45)
        cv2.line(frame, (bottom_x, height - 1), (top_x, int(height * 0.56)), (15, 15, 15), 16)
        return frame
