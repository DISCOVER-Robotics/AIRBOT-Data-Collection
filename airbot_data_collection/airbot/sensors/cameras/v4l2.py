from __future__ import annotations

from typing import Dict, Union

from numpy import ndarray

from airbot_data_collection.common.robot_devices.cameras.v4l2 import (
    V4L2Camera, V4L2CameraConfig)
from airbot_data_collection.utils import get_stamp_ms


class BsonV4L2Camera(V4L2Camera):

    config: V4L2CameraConfig

    def capture_observation(
        self,
    ) -> dict[str, dict[str, int | bytes | ndarray]]:
        return {
            "camera/color_image": {
                "t": get_stamp_ms(),
                "data": super().capture_observation(),
            }
        }
