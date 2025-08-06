from numpy import ndarray
from typing import Union
from airbot_data_collection.common.devices.cameras.v4l2 import (
    V4L2Camera,
    V4L2CameraConfig,
)
from time import time_ns


class BsonV4L2Camera(V4L2Camera):
    config: V4L2CameraConfig

    def capture_observation(
        self,
    ) -> dict[str, dict[str, Union[ndarray, int, bytes]]]:
        return {
            "color/image_raw": {
                "t": time_ns(),
                "data": super().capture_observation(),
            }
        }
