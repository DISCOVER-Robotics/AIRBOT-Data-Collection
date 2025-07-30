from numpy import ndarray

from airbot_data_collection.common.robot_devices.cameras.v4l2 import (
    V4L2Camera,
    V4L2CameraConfig,
)
from time import time_ns


class BsonV4L2Camera(V4L2Camera):
    config: V4L2CameraConfig

    def capture_observation(
        self,
    ) -> dict[str, dict[str, int | bytes | ndarray]]:
        return {
            "color/image_raw": {
                "t": time_ns(),
                "data": super().capture_observation(),
            }
        }
